"""Todo platform for Listonic integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ListonicItem, ListonicList
from .const import DOMAIN
from .coordinator import ListonicDataUpdateCoordinator

if TYPE_CHECKING:
    from . import ListonicConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ListonicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Listonic todo entities."""
    coordinator = entry.runtime_data

    entities = [
        ListonicTodoListEntity(coordinator, list_id)
        for list_id in coordinator.data
    ]

    async_add_entities(entities)

    # Register listener for new lists
    @callback
    def async_check_new_lists() -> None:
        """Check for new lists and add entities."""
        existing_list_ids = {
            entity.list_id
            for entity in hass.data.get(DOMAIN, {}).get("entities", [])
        }
        new_lists = [
            list_id
            for list_id in coordinator.data
            if list_id not in existing_list_ids
        ]
        if new_lists:
            async_add_entities(
                [
                    ListonicTodoListEntity(coordinator, list_id)
                    for list_id in new_lists
                ]
            )

    entry.async_on_unload(coordinator.async_add_listener(async_check_new_lists))


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
        await self.coordinator.async_add_item(
            self.list_id,
            item.summary,
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
        else:
            # Update other properties
            updates = {}
            if item.description is not None:
                updates["description"] = item.description
            if updates:
                await self.coordinator.async_update_item(
                    self.list_id, item_id, **updates
                )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete todo items."""
        for uid in uids:
            item_id = int(uid)
            await self.coordinator.async_delete_item(self.list_id, item_id)
