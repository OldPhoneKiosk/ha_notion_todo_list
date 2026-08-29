"""Data coordinator for Notion Todo List."""

from __future__ import annotations

from datetime import timedelta
from inspect import signature

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NotionApiError, NotionClient, NotionTodoConfig, NotionTodoItem
from .config_flow import _config_from_input
from .const import DOMAIN


class NotionTodoCoordinator(DataUpdateCoordinator[list[NotionTodoItem]]):
    """Fetch and mutate one Notion database as a todo list."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.config: NotionTodoConfig = _config_from_input(entry.data)
        self.client = NotionClient(async_get_clientsession(hass), self.config)
        kwargs = {
            "logger": __import__("logging").getLogger(__name__),
            "name": f"{DOMAIN}_{entry.entry_id}",
            "update_interval": timedelta(minutes=5),
        }
        if "config_entry" in signature(DataUpdateCoordinator.__init__).parameters:
            kwargs["config_entry"] = entry
        super().__init__(hass, **kwargs)

    async def _async_update_data(self) -> list[NotionTodoItem]:
        try:
            return await self.client.list_items()
        except NotionApiError as exc:
            raise UpdateFailed(str(exc)) from exc
