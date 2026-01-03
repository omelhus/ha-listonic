"""Data update coordinator for Listonic."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    ListonicApiClient,
    ListonicApiError,
    ListonicAuthError,
    ListonicItem,
    ListonicList,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ListonicDataUpdateCoordinator(
    TimestampDataUpdateCoordinator[dict[int, ListonicList]]
):
    """Class to manage fetching Listonic data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: ListonicApiClient,
        entry: ConfigEntry,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.config_entry = entry

    async def _async_update_data(self) -> dict[int, ListonicList]:
        """Fetch data from Listonic API."""
        try:
            lists = await self.client.get_lists()
            return {lst.id: lst for lst in lists}
        except ListonicAuthError as err:
            raise ConfigEntryAuthFailed("Invalid credentials") from err
        except ListonicApiError as err:
            raise UpdateFailed(f"Error communicating with Listonic API: {err}") from err

    async def async_add_item(
        self,
        list_id: int,
        name: str,
        quantity: str | None = None,
        unit: str | None = None,
    ) -> None:
        """Add an item to a list."""
        await self.client.add_item(list_id, name, quantity, unit)
        await self.async_request_refresh()

    async def async_update_item(
        self,
        list_id: int,
        item_id: int,
        *,
        is_checked: bool | None = None,
        name: str | None = None,
        quantity: str | None = None,
        unit: str | None = None,
        description: str | None = None,
        current_item: ListonicItem | None = None,
    ) -> None:
        """Update an item.

        Args:
            list_id: The ID of the list containing the item.
            item_id: The ID of the item to update.
            is_checked: Whether the item is checked off.
            name: The item name.
            quantity: The quantity (e.g., "2", "500g").
            unit: The unit of measurement.
            description: Additional description/notes.
            current_item: Optional current item state for optimistic updates.
        """
        await self.client.update_item(
            list_id,
            item_id,
            is_checked=is_checked,
            name=name,
            quantity=quantity,
            unit=unit,
            description=description,
            current_item=current_item,
        )
        await self.async_request_refresh()

    async def async_check_item(self, list_id: int, item_id: int) -> None:
        """Check an item."""
        await self.client.check_item(list_id, item_id)
        await self.async_request_refresh()

    async def async_uncheck_item(self, list_id: int, item_id: int) -> None:
        """Uncheck an item."""
        await self.client.uncheck_item(list_id, item_id)
        await self.async_request_refresh()

    async def async_delete_item(self, list_id: int, item_id: int) -> None:
        """Delete an item."""
        await self.client.delete_item(list_id, item_id)
        await self.async_request_refresh()

    async def async_delete_items(
        self, list_id: int, item_ids: list[int]
    ) -> None:
        """Delete multiple items with a single refresh at the end."""
        for item_id in item_ids:
            await self.client.delete_item(list_id, item_id)
        await self.async_request_refresh()

    async def async_update_list(self, list_id: int, *, name: str) -> None:
        """Update a list's name."""
        await self.client.update_list(list_id, name=name)
        await self.async_request_refresh()
