"""Config flow for Notion Todo List."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import NotionApiError, NotionAuthError, NotionClient, NotionTodoConfig
from .const import (
    CONF_ACTIVE_STATUS,
    CONF_COMPLETED_STATUS,
    CONF_DATABASE_ID,
    CONF_DESCRIPTION_PROPERTY,
    CONF_DUE_PROPERTY,
    CONF_FILTER_JSON,
    CONF_LIST_NAME,
    CONF_SORTS_JSON,
    CONF_STATUS_PROPERTY,
    CONF_TITLE_PROPERTY,
    DEFAULT_ACTIVE_STATUS,
    DEFAULT_COMPLETED_STATUS,
    DEFAULT_DESCRIPTION_PROPERTY,
    DEFAULT_DUE_PROPERTY,
    DEFAULT_STATUS_PROPERTY,
    DEFAULT_TITLE_PROPERTY,
    DOMAIN,
)


class NotionTodoListConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Notion Todo List."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                config = _config_from_input(user_input)
                await NotionClient(async_create_clientsession(self.hass), config).validate()
            except ValueError:
                errors["base"] = "invalid_json"
            except NotionAuthError:
                errors["base"] = "auth"
            except NotionApiError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(config.database_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_LIST_NAME) or "Notion Todo List",
                    data=user_input,
                )

        suggested = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_DATABASE_ID, default=suggested.get(CONF_DATABASE_ID, "")
                    ): str,
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
                        default=suggested.get(
                            CONF_DESCRIPTION_PROPERTY, DEFAULT_DESCRIPTION_PROPERTY
                        ),
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
                }
            ),
            errors=errors,
        )


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
    )
