"""Notion database backed Home Assistant to-do lists."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN, PLATFORMS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Notion Todo List from a config entry."""
    from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

    from .api import NotionApiError, NotionAuthError
    from .coordinator import NotionTodoCoordinator

    coordinator = NotionTodoCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except NotionAuthError as err:
        raise ConfigEntryAuthFailed("Notion token or database sharing is invalid") from err
    except NotionApiError as err:
        raise ConfigEntryNotReady(str(err)) from err
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
