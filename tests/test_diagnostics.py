"""Tests for the Listonic diagnostics module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from custom_components.listonic.api import ListonicItem, ListonicList
from custom_components.listonic.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from custom_components.listonic.diagnostics import async_get_config_entry_diagnostics


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock()


@pytest.fixture
def mock_client():
    """Create a mock Listonic API client."""
    client = MagicMock()
    client._token = "test_access_token"
    client._refresh_token = "test_refresh_token"
    return client


@pytest.fixture
def sample_lists():
    """Create sample ListonicList objects."""
    return {
        123: ListonicList(
            id=123,
            name="Groceries",
            items=[
                ListonicItem(id=1, name="Milk", is_checked=False),
                ListonicItem(id=2, name="Bread", is_checked=True),
                ListonicItem(id=3, name="Eggs", is_checked=True),
            ],
            is_archived=False,
        ),
        456: ListonicList(
            id=456,
            name="Hardware",
            items=[
                ListonicItem(id=4, name="Screws", is_checked=False),
            ],
            is_archived=True,
        ),
    }


@pytest.fixture
def mock_coordinator(mock_client, sample_lists):
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.client = mock_client
    coordinator.data = sample_lists
    coordinator.last_update_success = True
    coordinator.last_update_success_time = datetime(2024, 1, 15, 10, 30, 0)
    return coordinator


@pytest.fixture
def mock_config_entry(mock_coordinator):
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {
        CONF_EMAIL: "user@example.com",
        CONF_PASSWORD: "supersecretpassword",
    }
    entry.options = {}
    entry.runtime_data = mock_coordinator
    return entry


class TestAsyncGetConfigEntryDiagnostics:
    """Tests for async_get_config_entry_diagnostics."""

    @pytest.mark.asyncio
    async def test_returns_expected_structure(
        self, mock_hass, mock_config_entry
    ):
        """Test that diagnostics returns expected top-level keys."""
        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        assert isinstance(result, dict)
        assert "config_entry" in result
        assert "lists" in result
        assert "coordinator" in result
        assert "authentication" in result

    @pytest.mark.asyncio
    async def test_sensitive_data_is_redacted(
        self, mock_hass, mock_config_entry
    ):
        """Test that email and password are redacted in diagnostics."""
        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        config_entry_data = result["config_entry"]
        assert config_entry_data[CONF_EMAIL] == "**REDACTED**"
        assert config_entry_data[CONF_PASSWORD] == "**REDACTED**"

    @pytest.mark.asyncio
    async def test_list_info_includes_counts(
        self, mock_hass, mock_config_entry
    ):
        """Test that list info includes item counts and details."""
        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        lists_info = result["lists"]
        assert lists_info["count"] == 2
        assert len(lists_info["details"]) == 2

        # Find grocery list details
        grocery_list = next(
            (d for d in lists_info["details"] if d["list_id"] == 123), None
        )
        assert grocery_list is not None
        assert grocery_list["item_count"] == 3
        assert grocery_list["checked_count"] == 2
        assert grocery_list["unchecked_count"] == 1
        assert grocery_list["is_archived"] is False

        # Find hardware list details
        hardware_list = next(
            (d for d in lists_info["details"] if d["list_id"] == 456), None
        )
        assert hardware_list is not None
        assert hardware_list["item_count"] == 1
        assert hardware_list["checked_count"] == 0
        assert hardware_list["unchecked_count"] == 1
        assert hardware_list["is_archived"] is True

    @pytest.mark.asyncio
    async def test_coordinator_info_includes_update_status(
        self, mock_hass, mock_config_entry
    ):
        """Test that coordinator info includes last_update_success and time."""
        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        coordinator_info = result["coordinator"]
        assert coordinator_info["last_update_success"] is True
        assert coordinator_info["last_update_time"] == "2024-01-15T10:30:00"
        assert coordinator_info["update_interval_seconds"] == DEFAULT_SCAN_INTERVAL

    @pytest.mark.asyncio
    async def test_coordinator_info_with_none_update_time(
        self, mock_hass, mock_config_entry
    ):
        """Test coordinator info when last_update_success_time is None."""
        mock_config_entry.runtime_data.last_update_success_time = None

        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        coordinator_info = result["coordinator"]
        assert coordinator_info["last_update_time"] is None

    @pytest.mark.asyncio
    async def test_authentication_info_shows_token_status(
        self, mock_hass, mock_config_entry
    ):
        """Test that authentication info shows token presence status."""
        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        auth_info = result["authentication"]
        assert auth_info["has_token"] is True
        assert auth_info["has_refresh_token"] is True

    @pytest.mark.asyncio
    async def test_authentication_info_when_tokens_missing(
        self, mock_hass, mock_config_entry
    ):
        """Test authentication info when tokens are not present."""
        mock_config_entry.runtime_data.client._token = None
        mock_config_entry.runtime_data.client._refresh_token = None

        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        auth_info = result["authentication"]
        assert auth_info["has_token"] is False
        assert auth_info["has_refresh_token"] is False

    @pytest.mark.asyncio
    async def test_empty_lists_data(self, mock_hass, mock_config_entry):
        """Test diagnostics when coordinator has no lists."""
        mock_config_entry.runtime_data.data = {}

        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        lists_info = result["lists"]
        assert lists_info["count"] == 0
        assert lists_info["details"] == []

    @pytest.mark.asyncio
    async def test_none_coordinator_data(self, mock_hass, mock_config_entry):
        """Test diagnostics when coordinator data is None."""
        mock_config_entry.runtime_data.data = None

        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        lists_info = result["lists"]
        assert lists_info["count"] == 0
        assert lists_info["details"] == []

    @pytest.mark.asyncio
    async def test_coordinator_update_failure(
        self, mock_hass, mock_config_entry
    ):
        """Test diagnostics shows update failure status."""
        mock_config_entry.runtime_data.last_update_success = False

        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        coordinator_info = result["coordinator"]
        assert coordinator_info["last_update_success"] is False

    @pytest.mark.asyncio
    async def test_scan_interval_from_options_is_used(
        self, mock_hass, mock_config_entry
    ):
        """Test that scan_interval from options is used instead of default."""
        custom_interval = 120
        mock_config_entry.options = {CONF_SCAN_INTERVAL: custom_interval}

        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        coordinator_info = result["coordinator"]
        assert coordinator_info["update_interval_seconds"] == custom_interval

    @pytest.mark.asyncio
    async def test_scan_interval_defaults_when_not_in_options(
        self, mock_hass, mock_config_entry
    ):
        """Test that default scan_interval is used when not set in options."""
        mock_config_entry.options = {}

        result = await async_get_config_entry_diagnostics(
            mock_hass, mock_config_entry
        )

        coordinator_info = result["coordinator"]
        assert coordinator_info["update_interval_seconds"] == DEFAULT_SCAN_INTERVAL
