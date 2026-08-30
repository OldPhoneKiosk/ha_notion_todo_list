"""HA runtime smoke tests for Notion Todo List."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.todo import TodoItemStatus
from homeassistant.core import HomeAssistant

from custom_components.notion_todo_list.const import (
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
    DOMAIN,
)


class _FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return str(self.payload)


class _FakeSession:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers=None, json=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "json": json})
        response = dict(self.responses.pop(0))
        return _FakeResponse(response, response.pop("status", 200))


def _valid_input() -> dict[str, str]:
    return {
        "access_token": "secret",
        CONF_DATABASE_ID: "db1",
        CONF_LIST_NAME: "Notion Tasks",
        CONF_TITLE_PROPERTY: "Name",
        CONF_STATUS_PROPERTY: "Done",
        CONF_DUE_PROPERTY: "Due",
        CONF_DESCRIPTION_PROPERTY: "Description",
        CONF_FILTER_JSON: '{"property":"Project","relation":{"contains":"abc"}}',
        CONF_SORTS_JSON: '[{"property":"Due","direction":"ascending"}]',
        CONF_ACTIVE_STATUS: "false",
        CONF_COMPLETED_STATUS: "true",
        CONF_UPDATE_SECONDS: "45",
        CONF_DEFAULT_PROPERTY: "Assignee",
        CONF_DEFAULT_VALUE: "user-123",
    }


async def test_config_flow_validates_database_with_shared_ha_session(hass: HomeAssistant):
    session = _FakeSession(
        [
            {
                "properties": {
                    "Name": {"type": "title"},
                    "Done": {"type": "checkbox"},
                    "Due": {"type": "date"},
                    "Description": {"type": "rich_text"},
                    "Assignee": {"type": "people"},
                }
            }
        ]
    )
    with patch(
        "custom_components.notion_todo_list.config_flow.async_get_clientsession",
        return_value=session,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=_valid_input()
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Notion Tasks"
    assert session.calls[0]["method"] == "GET"
    assert session.calls[0]["url"].endswith("/databases/db1")


async def test_options_flow_updates_existing_entry(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    data = _valid_input()
    entry = MockConfigEntry(domain=DOMAIN, title="Notion Tasks", data=data)
    entry.add_to_hass(hass)
    session = _FakeSession(
        [
            {
                "properties": {
                    "Name": {"type": "title"},
                    "Done": {"type": "checkbox"},
                    "Due": {"type": "date"},
                    "Description": {"type": "rich_text"},
                    "Assignee": {"type": "people"},
                }
            }
        ]
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    updated = {key: value for key, value in data.items() if key != CONF_DATABASE_ID} | {
        CONF_UPDATE_SECONDS: 30,
        CONF_DEFAULT_VALUE: "user-456",
    }
    with patch(
        "custom_components.notion_todo_list.config_flow.async_get_clientsession",
        return_value=session,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input=updated
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UPDATE_SECONDS] == 30
    assert result["data"][CONF_DEFAULT_VALUE] == "user-456"


async def test_todo_entity_rebuilds_cached_todo_items_after_refresh(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.notion_todo_list.todo import NotionDatabaseTodoEntity

    entry = MockConfigEntry(domain=DOMAIN, title="Notion Tasks", data=_valid_input())
    coordinator = type("Coordinator", (), {})()
    coordinator.data = []
    coordinator.async_add_listener = lambda listener: lambda: None
    coordinator.last_update_success = True

    entity = NotionDatabaseTodoEntity(coordinator, entry)
    entity.async_write_ha_state = lambda: None
    entity._handle_coordinator_update()
    assert entity.todo_items == []

    coordinator.data = [
        type(
            "Item",
            (),
            {
                "uid": "p1",
                "summary": "Buy milk",
                "completed": False,
                "due": None,
                "description": None,
            },
        )()
    ]
    entity._handle_coordinator_update()

    assert len(entity.todo_items) == 1
    assert entity.todo_items[0].summary == "Buy milk"
    assert entity.todo_items[0].status == TodoItemStatus.NEEDS_ACTION
