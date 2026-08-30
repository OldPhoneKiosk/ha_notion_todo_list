"""Home Assistant todo platform for Notion Todo List."""

from __future__ import annotations

from typing import cast

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LIST_NAME, DOMAIN
from .coordinator import NotionTodoCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the todo entity."""
    coordinator: NotionTodoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NotionDatabaseTodoEntity(coordinator, entry)])


class NotionDatabaseTodoEntity(CoordinatorEntity[NotionTodoCoordinator], TodoListEntity):
    """A Notion database exposed as one HA todo list."""

    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DUE_DATETIME_ON_ITEM
    )

    def __init__(self, coordinator: NotionTodoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}"
        self._attr_name = entry.data.get(CONF_LIST_NAME) or entry.title

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data or []
        self._attr_todo_items = [
            TodoItem(
                uid=item.uid,
                summary=item.summary,
                status=TodoItemStatus.COMPLETED if item.completed else TodoItemStatus.NEEDS_ACTION,
                due=item.due,
                description=item.description,
            )
            for item in data
            if not item.completed
        ]
        self.__dict__.pop("todo_items", None)
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._handle_coordinator_update()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self.coordinator.client.create_item(
            item.summary,
            due=item.due,
            description=item.description,
        )
        await self.coordinator.async_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        uid = cast(str, item.uid)
        await self.coordinator.client.update_item(
            uid,
            summary=item.summary,
            completed=item.status == TodoItemStatus.COMPLETED if item.status is not None else None,
            due=item.due,
            description=item.description,
        )
        await self.coordinator.async_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        await self.coordinator.client.archive_items(uids)
        await self.coordinator.async_refresh()
