"""Tests for the Listonic integration setup."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.listonic import (
    PLATFORMS,
    _async_update_listener,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.listonic.api import (
    ListonicApiClient,
    ListonicAuthError,
    ListonicList,
)
from custom_components.listonic.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.listonic.coordinator import ListonicDataUpdateCoordinator


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.data = {}
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    hass.services.async_remove = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.data = {
        CONF_EMAIL: "test@example.com",
        CONF_PASSWORD: "testpassword",
    }
    entry.options = {}
    entry.entry_id = "test_entry_id"
    entry.title = "Listonic"
    entry.domain = DOMAIN
    entry.runtime_data = None
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    return entry


@pytest.fixture
def mock_api_client():
    """Create a mock API client."""
    client = MagicMock(spec=ListonicApiClient)
    client.authenticate = AsyncMock(return_value=True)
    client.get_lists = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock(spec=ListonicDataUpdateCoordinator)
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
    return coordinator


class TestAsyncSetupEntry:
    """Tests for async_setup_entry."""

    @pytest.mark.asyncio
    async def test_successful_setup(self, mock_hass, mock_config_entry):
        """Test successful setup of the integration."""
        mock_lists = [
            ListonicList(id=1, name="Groceries", items=[], is_archived=False),
            ListonicList(id=2, name="Hardware", items=[], is_archived=False),
        ]

        with (
            patch(
                "custom_components.listonic.async_get_clientsession"
            ) as mock_session,
            patch(
                "custom_components.listonic.ListonicApiClient"
            ) as mock_client_class,
            patch(
                "custom_components.listonic.ListonicDataUpdateCoordinator"
            ) as mock_coord_class,
        ):
            mock_session.return_value = MagicMock()
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coordinator.data = {lst.id: lst for lst in mock_lists}
            mock_coord_class.return_value = mock_coordinator

            result = await async_setup_entry(mock_hass, mock_config_entry)

            assert result is True
            mock_client.authenticate.assert_called_once()
            mock_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_hass.config_entries.async_forward_entry_setups.assert_called_once_with(
                mock_config_entry, PLATFORMS
            )
            assert mock_config_entry.runtime_data == mock_coordinator
            mock_config_entry.async_on_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_error_raises_config_entry_auth_failed(
        self, mock_hass, mock_config_entry
    ):
        """Test that authentication errors raise ConfigEntryAuthFailed."""
        with (
            patch(
                "custom_components.listonic.async_get_clientsession"
            ) as mock_session,
            patch(
                "custom_components.listonic.ListonicApiClient"
            ) as mock_client_class,
        ):
            mock_session.return_value = MagicMock()
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(
                side_effect=ListonicAuthError("Invalid credentials")
            )
            mock_client_class.return_value = mock_client

            with pytest.raises(ConfigEntryAuthFailed, match="Invalid credentials"):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_api_error_during_refresh_raises_config_entry_not_ready(
        self, mock_hass, mock_config_entry
    ):
        """Test that API errors during first refresh raise ConfigEntryNotReady."""
        with (
            patch(
                "custom_components.listonic.async_get_clientsession"
            ) as mock_session,
            patch(
                "custom_components.listonic.ListonicApiClient"
            ) as mock_client_class,
            patch(
                "custom_components.listonic.ListonicDataUpdateCoordinator"
            ) as mock_coord_class,
        ):
            mock_session.return_value = MagicMock()
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock(
                side_effect=ConfigEntryNotReady("API error")
            )
            mock_coord_class.return_value = mock_coordinator

            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_setup_uses_custom_scan_interval(self, mock_hass, mock_config_entry):
        """Test that setup respects custom scan interval from options."""
        custom_interval = 60
        mock_config_entry.options = {CONF_SCAN_INTERVAL: custom_interval}

        with (
            patch(
                "custom_components.listonic.async_get_clientsession"
            ) as mock_session,
            patch(
                "custom_components.listonic.ListonicApiClient"
            ) as mock_client_class,
            patch(
                "custom_components.listonic.ListonicDataUpdateCoordinator"
            ) as mock_coord_class,
        ):
            mock_session.return_value = MagicMock()
            mock_client = MagicMock()
            mock_client.authenticate = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            mock_coordinator = MagicMock()
            mock_coordinator.async_config_entry_first_refresh = AsyncMock()
            mock_coord_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            # Verify coordinator was created with custom scan interval
            mock_coord_class.assert_called_once()
            call_kwargs = mock_coord_class.call_args
            assert call_kwargs.kwargs.get("scan_interval") == custom_interval


class TestAsyncUnloadEntry:
    """Tests for async_unload_entry."""

    @pytest.mark.asyncio
    async def test_unload_entry_success(self, mock_hass, mock_config_entry):
        """Test successful unloading of the integration."""
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        # Set up hass.data as it would be after setup
        mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: MagicMock()}

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        mock_hass.config_entries.async_unload_platforms.assert_called_once_with(
            mock_config_entry, PLATFORMS
        )
        # Verify data and services were cleaned up
        assert DOMAIN not in mock_hass.data
        mock_hass.services.async_remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_unload_entry_failure(self, mock_hass, mock_config_entry):
        """Test failed unloading of the integration."""
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        # Set up hass.data as it would be after setup
        mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: MagicMock()}

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is False
        # Data should not be cleaned up on failure
        assert DOMAIN in mock_hass.data


class TestAsyncUpdateListener:
    """Tests for _async_update_listener."""

    @pytest.mark.asyncio
    async def test_update_listener_updates_scan_interval(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
        """Test that options update listener updates coordinator interval."""
        new_interval = 120
        mock_config_entry.options = {CONF_SCAN_INTERVAL: new_interval}
        mock_config_entry.runtime_data = mock_coordinator

        await _async_update_listener(mock_hass, mock_config_entry)

        assert mock_coordinator.update_interval == timedelta(seconds=new_interval)

    @pytest.mark.asyncio
    async def test_update_listener_uses_default_when_not_set(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
        """Test that options update listener uses default interval when not set."""
        mock_config_entry.options = {}  # No scan interval in options
        mock_config_entry.runtime_data = mock_coordinator

        await _async_update_listener(mock_hass, mock_config_entry)

        assert mock_coordinator.update_interval == timedelta(
            seconds=DEFAULT_SCAN_INTERVAL
        )


class TestPlatforms:
    """Tests for platform configuration."""

    def test_platforms_contains_todo(self):
        """Test that PLATFORMS includes the TODO platform."""
        assert Platform.TODO in PLATFORMS

    def test_platforms_list(self):
        """Test PLATFORMS is a list with expected content."""
        assert isinstance(PLATFORMS, list)
        assert len(PLATFORMS) == 1
