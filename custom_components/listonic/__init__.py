"""The Listonic integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
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

ATTR_LIST_ID = "list_id"
SERVICE_RENAME_LIST = "rename_list"

SERVICE_RENAME_LIST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_LIST_ID): cv.positive_int,
        vol.Required(ATTR_NAME): cv.string,
    }
)


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

    # Store coordinator in hass.data for service access
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_RENAME_LIST):
        async def async_rename_list(call: ServiceCall) -> None:
            """Handle rename list service call."""
            list_id = call.data[ATTR_LIST_ID]
            name = call.data[ATTR_NAME]

            # Find the coordinator that has this list
            for coordinator in hass.data[DOMAIN].values():
                if not isinstance(coordinator, ListonicDataUpdateCoordinator):
                    continue
                if list_id in coordinator.data:
                    await coordinator.async_update_list(list_id, name=name)
                    return

            _LOGGER.error("List %s not found in any Listonic account", list_id)

        hass.services.async_register(
            DOMAIN,
            SERVICE_RENAME_LIST,
            async_rename_list,
            schema=SERVICE_RENAME_LIST_SCHEMA,
        )

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
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        # Remove services if this was the last entry
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            hass.services.async_remove(DOMAIN, SERVICE_RENAME_LIST)

    return unload_ok
