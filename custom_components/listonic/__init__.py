"""The Listonic integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ListonicApiClient
from .const import CONF_EMAIL, CONF_PASSWORD
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

    # Authenticate on setup
    await client.authenticate()

    coordinator = ListonicDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ListonicConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
