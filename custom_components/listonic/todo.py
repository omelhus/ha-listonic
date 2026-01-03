"""Todo platform for Listonic integration."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ListonicItem, ListonicList
from .const import DOMAIN
from .coordinator import ListonicDataUpdateCoordinator

if TYPE_CHECKING:
    from . import ListonicConfigEntry

_LOGGER = logging.getLogger(__name__)

# Pattern to match "(quantity unit)" or "(quantity)" at end of string
_QUANTITY_PATTERN = re.compile(r"^(.+?)\s*\((\d+(?:[.,]\d+)?)\s*([^)]*)\)\s*$")


def _parse_item_summary(summary: str) -> tuple[str, str | None, str | None]:
    """Parse item name, quantity, and unit from summary.

    Examples:
        "Milk (2 L)" -> ("Milk", "2", "L")
        "Eggs (12)" -> ("Eggs", "12", None)
        "Bread" -> ("Bread", None, None)
        "Butter (0.5 kg)" -> ("Butter", "0.5", "kg")
    """
    match = _QUANTITY_PATTERN.match(summary)
    if not match:
        return (summary.strip(), None, None)

    name = match.group(1).strip()
    quantity = match.group(2)
    unit = match.group(3).strip() if match.group(3).strip() else None

    return (name, quantity, unit)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ListonicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Listonic todo entities."""
    coordinator = entry.runtime_data

    # Track list IDs that have entities created
    known_list_ids: set[int] = set(coordinator.data.keys())

    entities = [
        ListonicTodoListEntity(coordinator, list_id)
        for list_id in known_list_ids
    ]

    async_add_entities(entities)

    # Register listener for new and deleted lists
    @callback
    def async_check_lists() -> None:
        """Check for new and deleted lists."""
        if not coordinator.data:
            # Don't process if coordinator data is empty/None - likely a temporary issue
            return

        current_list_ids = set(coordinator.data.keys())

        # Handle new lists
        new_list_ids = current_list_ids - known_list_ids
        if new_list_ids:
            known_list_ids.update(new_list_ids)
            async_add_entities(
                [
                    ListonicTodoListEntity(coordinator, list_id)
                    for list_id in new_list_ids
                ]
            )

        # Handle deleted lists - only if we still have some lists
        # This prevents mass deletion if API temporarily returns empty
        deleted_list_ids = known_list_ids - current_list_ids
        if deleted_list_ids and current_list_ids:
            ent_reg = er.async_get(hass)
            for list_id in deleted_list_ids:
                unique_id = f"listonic_{list_id}"
                entity_id = ent_reg.async_get_entity_id(
                    "todo", DOMAIN, unique_id
                )
                if entity_id:
                    _LOGGER.debug("Removing entity for deleted list: %s", list_id)
                    ent_reg.async_remove(entity_id)
            known_list_ids.difference_update(deleted_list_ids)

    entry.async_on_unload(coordinator.async_add_listener(async_check_lists))


class ListonicTodoListEntity(
    CoordinatorEntity[ListonicDataUpdateCoordinator], TodoListEntity
):
    """A Listonic shopping list as a todo entity."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(
        self,
        coordinator: ListonicDataUpdateCoordinator,
        list_id: int,
    ) -> None:
        """Initialize the todo entity."""
        super().__init__(coordinator)
        self.list_id = list_id
        self._attr_unique_id = f"listonic_{list_id}"

    @property
    def _list(self) -> ListonicList | None:
        """Get the current list data."""
        return self.coordinator.data.get(self.list_id)

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        if self._list:
            return self._list.name
        return f"Listonic List {self.list_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this Listonic account."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="Listonic",
            manufacturer="Listonic",
            model="Shopping Lists",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Return the todo items."""
        if not self._list:
            return None

        return [
            self._item_to_todo_item(item)
            for item in self._list.items
        ]

    @staticmethod
    def _item_to_todo_item(item: ListonicItem) -> TodoItem:
        """Convert a Listonic item to a TodoItem."""
        status = (
            TodoItemStatus.COMPLETED if item.is_checked else TodoItemStatus.NEEDS_ACTION
        )

        # Build summary with quantity if present
        summary = item.name
        if item.quantity:
            if item.unit:
                summary = f"{item.name} ({item.quantity} {item.unit})"
            else:
                summary = f"{item.name} ({item.quantity})"

        return TodoItem(
            uid=str(item.id),
            summary=summary,
            status=status,
            description=item.description,
        )

    def _find_item_by_uid(self, uid: str) -> ListonicItem | None:
        """Find an item by its UID."""
        if not self._list:
            return None
        item_id = int(uid)
        for item in self._list.items:
            if item.id == item_id:
                return item
        return None

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a new todo item."""
        if not item.summary:
            return

        name, quantity, unit = _parse_item_summary(item.summary)
        await self.coordinator.async_add_item(
            self.list_id,
            name,
            quantity=quantity,
            unit=unit,
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update a todo item."""
        if not item.uid:
            return

        item_id = int(item.uid)
        existing_item = self._find_item_by_uid(item.uid)

        if not existing_item:
            return

        # Check if status changed
        is_checked = item.status == TodoItemStatus.COMPLETED
        if is_checked != existing_item.is_checked:
            if is_checked:
                await self.coordinator.async_check_item(self.list_id, item_id)
            else:
                await self.coordinator.async_uncheck_item(self.list_id, item_id)
        elif item.description is not None:
            # Update description when status unchanged
            await self.coordinator.async_update_item(
                self.list_id, item_id, description=item.description
            )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete todo items."""
        item_ids = [int(uid) for uid in uids]
        await self.coordinator.async_delete_items(self.list_id, item_ids)
