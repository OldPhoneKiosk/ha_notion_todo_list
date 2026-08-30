"""Config and options flow for Notion Todo List."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NotionApiError, NotionAuthError, NotionClient, NotionTodoConfig
from .const import (
    CONF_ACTIVE_STATUS,
    CONF_COMPLETED_STATUS,
    CONF_DATABASE_ID,
    CONF_DEFAULT_PROPERTY,
    CONF_DEFAULT_VALUE,
    CONF_DESCRIPTION_PROPERTY,
    CONF_DUE_PROPERTY,
    CONF_FILTER_JSON,
    CONF_LIST_NAME,
    CONF_SORTS_JSON,
    CONF_STATUS_PROPERTY,
    CONF_TITLE_PROPERTY,
    CONF_UPDATE_SECONDS,
    DEFAULT_ACTIVE_STATUS,
    DEFAULT_COMPLETED_STATUS,
    DEFAULT_DESCRIPTION_PROPERTY,
    DEFAULT_DUE_PROPERTY,
    DEFAULT_STATUS_PROPERTY,
    DEFAULT_TITLE_PROPERTY,
    DEFAULT_UPDATE_SECONDS,
    DOMAIN,
)


class NotionTodoListConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Notion Todo List."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow so existing entities can be edited in HA."""
        return NotionTodoListOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate_input(self.hass, user_input)
            if not errors:
                config = _config_from_input(user_input)
                await self.async_set_unique_id(config.database_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_LIST_NAME) or "Notion Todo List",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}, include_token=True, include_database=True),
            errors=errors,
        )


class NotionTodoListOptionsFlow(config_entries.OptionsFlow):
    """Edit an existing Notion Todo List config entry."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        current = _entry_config(self.entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            updated = {**current, **user_input}
            # Do not allow options flow to silently change database identity; keep the field visible
            # in the initial add flow only. Users can create a second entity for another database.
            updated[CONF_DATABASE_ID] = current[CONF_DATABASE_ID]
            errors = await _validate_input(self.hass, updated)
            if not errors:
                return self.async_create_entry(title="", data=updated)

        return self.async_show_form(
            step_id="init",
            data_schema=_schema(current, include_token=True, include_database=False),
            errors=errors,
        )


async def _validate_input(hass, data: dict[str, Any]) -> dict[str, str]:
    try:
        config = _config_from_input(data)
        await NotionClient(async_get_clientsession(hass), config).validate()
    except ValueError:
        return {"base": "invalid_json"}
    except NotionAuthError:
        return {"base": "auth"}
    except NotionApiError:
        return {"base": "unknown"}
    return {}


def _schema(
    suggested: dict[str, Any], *, include_token: bool, include_database: bool
) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if include_token:
        fields[vol.Required(CONF_ACCESS_TOKEN, default=suggested.get(CONF_ACCESS_TOKEN, ""))] = (
            selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
        )
    if include_database:
        fields[vol.Required(CONF_DATABASE_ID, default=suggested.get(CONF_DATABASE_ID, ""))] = str
    fields.update(
        {
            vol.Required(
                CONF_LIST_NAME, default=suggested.get(CONF_LIST_NAME, "Notion Tasks")
            ): str,
            vol.Required(
                CONF_TITLE_PROPERTY,
                default=suggested.get(CONF_TITLE_PROPERTY, DEFAULT_TITLE_PROPERTY),
            ): str,
            vol.Required(
                CONF_STATUS_PROPERTY,
                default=suggested.get(CONF_STATUS_PROPERTY, DEFAULT_STATUS_PROPERTY),
            ): str,
            vol.Optional(
                CONF_DUE_PROPERTY,
                default=suggested.get(CONF_DUE_PROPERTY, DEFAULT_DUE_PROPERTY),
            ): str,
            vol.Optional(
                CONF_DESCRIPTION_PROPERTY,
                default=suggested.get(CONF_DESCRIPTION_PROPERTY, DEFAULT_DESCRIPTION_PROPERTY),
            ): str,
            vol.Optional(
                CONF_FILTER_JSON, default=suggested.get(CONF_FILTER_JSON, "")
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Optional(
                CONF_SORTS_JSON, default=suggested.get(CONF_SORTS_JSON, "")
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required(
                CONF_ACTIVE_STATUS,
                default=suggested.get(CONF_ACTIVE_STATUS, DEFAULT_ACTIVE_STATUS),
            ): str,
            vol.Required(
                CONF_COMPLETED_STATUS,
                default=suggested.get(CONF_COMPLETED_STATUS, DEFAULT_COMPLETED_STATUS),
            ): str,
            vol.Required(
                CONF_UPDATE_SECONDS,
                default=int(suggested.get(CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS)),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=15, max=86400, step=1, mode="box")
            ),
            vol.Optional(
                CONF_DEFAULT_PROPERTY, default=suggested.get(CONF_DEFAULT_PROPERTY, "")
            ): str,
            vol.Optional(CONF_DEFAULT_VALUE, default=suggested.get(CONF_DEFAULT_VALUE, "")): str,
        }
    )
    return vol.Schema(fields)


def _entry_config(entry: config_entries.ConfigEntry) -> dict[str, Any]:
    return {**entry.data, **entry.options}


def _json_or_none(raw: str | None, expected: type) -> Any | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, expected):
        raise ValueError(f"expected {expected.__name__}")
    return parsed


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(15, parsed)


def _config_from_input(data: dict[str, Any]) -> NotionTodoConfig:
    return NotionTodoConfig(
        token=data[CONF_ACCESS_TOKEN],
        database_id=data[CONF_DATABASE_ID].strip(),
        title_property=data[CONF_TITLE_PROPERTY].strip(),
        status_property=data[CONF_STATUS_PROPERTY].strip(),
        due_property=_blank_to_none(data.get(CONF_DUE_PROPERTY)),
        description_property=_blank_to_none(data.get(CONF_DESCRIPTION_PROPERTY)),
        filter_obj=_json_or_none(data.get(CONF_FILTER_JSON), dict),
        sorts_obj=_json_or_none(data.get(CONF_SORTS_JSON), list),
        active_status=data.get(CONF_ACTIVE_STATUS, DEFAULT_ACTIVE_STATUS).strip(),
        completed_status=data.get(CONF_COMPLETED_STATUS, DEFAULT_COMPLETED_STATUS).strip(),
        update_seconds=_positive_int(data.get(CONF_UPDATE_SECONDS), DEFAULT_UPDATE_SECONDS),
        default_property=_blank_to_none(data.get(CONF_DEFAULT_PROPERTY)),
        default_value=_blank_to_none(data.get(CONF_DEFAULT_VALUE)),
    )
