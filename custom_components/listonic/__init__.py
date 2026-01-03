"""The Listonic integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ListonicApiClient, ListonicAuthError
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .const import DOMAIN as DOMAIN
from .coordinator import ListonicDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TODO]

type ListonicConfigEntry = ConfigEntry[ListonicDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ListonicConfigEntry) -> bool:
    """Set up Listonic from a config entry."""
    session = async_get_clientsession(hass)

    client = ListonicApiClient(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )

    # Authenticate on setup - raises ConfigEntryAuthFailed to trigger reauth
    try:
        await client.authenticate()
    except ListonicAuthError as err:
        raise ConfigEntryAuthFailed("Invalid credentials") from err

    # Get scan interval from options, falling back to default
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = ListonicDataUpdateCoordinator(
        hass, client, entry, scan_interval=scan_interval
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise  # Re-raise auth errors as-is
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to fetch initial data: {err}") from err

    entry.runtime_data = coordinator

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ListonicConfigEntry
) -> None:
    """Handle options update."""
    coordinator = entry.runtime_data
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator.update_interval = timedelta(seconds=scan_interval)
    _LOGGER.debug("Updated scan interval to %s seconds", scan_interval)


async def async_unload_entry(hass: HomeAssistant, entry: ListonicConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
