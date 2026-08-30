from __future__ import annotations

from datetime import date

import pytest

from custom_components.notion_todo_list.api import NotionClient, NotionTodoConfig


class FakeResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return str(self.payload)


class FakeSession:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers=None, json=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "json": json})
        payload = self.responses.pop(0)
        return FakeResponse(payload.pop("status", 200), payload)


def cfg(**overrides):
    base = dict(
        token="secret",
        database_id="db1",
        title_property="Name",
        status_property="Done",
        due_property="Due",
        description_property="Description",
        filter_obj={"property": "Project", "relation": {"contains": "proj1"}},
        sorts_obj=[{"property": "Due", "direction": "ascending"}],
        active_status="false",
        completed_status="true",
    )
    base.update(overrides)
    return NotionTodoConfig(**base)


def database_schema(status_type="checkbox"):
    return {
        "properties": {
            "Name": {"type": "title"},
            "Done": {"type": status_type},
            "Due": {"type": "date"},
            "Description": {"type": "rich_text"},
            "Assignee": {"type": "people"},
            "Priority": {"type": "select"},
        }
    }


def page(page_id="p1", done=False):
    return {
        "object": "page",
        "id": page_id,
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "Buy milk"}]},
            "Done": {"type": "checkbox", "checkbox": done},
            "Due": {"type": "date", "date": {"start": "2026-08-30"}},
            "Description": {"type": "rich_text", "rich_text": [{"plain_text": "2 bottles"}]},
        },
    }


@pytest.mark.asyncio
async def test_query_passes_filter_and_sorts_and_maps_items():
    session = FakeSession(
        [
            {"results": [page("p1", False), page("p2", True)], "has_more": False},
        ]
    )
    client = NotionClient(session, cfg())

    items = await client.list_items()

    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["json"]["filter"] == {
        "property": "Project",
        "relation": {"contains": "proj1"},
    }
    assert session.calls[0]["json"]["sorts"] == [{"property": "Due", "direction": "ascending"}]
    assert items[0].uid == "p1"
    assert items[0].summary == "Buy milk"
    assert items[0].due == date(2026, 8, 30)
    assert items[0].description == "2 bottles"
    assert items[1].completed is True


@pytest.mark.asyncio
async def test_create_uses_checkbox_status_when_database_property_is_checkbox():
    session = FakeSession([database_schema("checkbox"), {}])
    client = NotionClient(session, cfg())

    await client.create_item("Walk dog", due=date(2026, 9, 1), description="evening")

    body = session.calls[-1]["json"]
    assert body["parent"] == {"database_id": "db1"}
    assert body["properties"]["Name"]["title"][0]["text"]["content"] == "Walk dog"
    assert body["properties"]["Done"] == {"checkbox": False}
    assert body["properties"]["Due"] == {"date": {"start": "2026-09-01"}}


@pytest.mark.asyncio
async def test_update_uses_status_name_when_database_property_is_status():
    session = FakeSession([database_schema("status"), {}])
    client = NotionClient(session, cfg(active_status="Todo", completed_status="Done"))

    await client.update_item("p1", completed=True, summary="Done task")

    body = session.calls[-1]["json"]
    assert body["properties"]["Done"] == {"status": {"name": "Done"}}
    assert body["properties"]["Name"]["title"][0]["text"]["content"] == "Done task"


@pytest.mark.asyncio
async def test_create_adds_default_people_property():
    session = FakeSession([database_schema("checkbox"), {}])
    client = NotionClient(session, cfg(default_property="Assignee", default_value="user-123"))

    await client.create_item("Assigned task")

    body = session.calls[-1]["json"]
    assert body["properties"]["Assignee"] == {"people": [{"id": "user-123"}]}


@pytest.mark.asyncio
async def test_create_adds_default_select_property():
    session = FakeSession([database_schema("checkbox"), {}])
    client = NotionClient(session, cfg(default_property="Priority", default_value="High"))

    await client.create_item("Priority task")

    body = session.calls[-1]["json"]
    assert body["properties"]["Priority"] == {"select": {"name": "High"}}


@pytest.mark.asyncio
async def test_archive_items_patches_pages_archived():
    session = FakeSession([{}, {}])
    client = NotionClient(session, cfg())

    await client.archive_items(["p1", "p2"])

    assert [call["url"].rsplit("/", 1)[-1] for call in session.calls] == ["p1", "p2"]
    assert all(call["json"] == {"archived": True} for call in session.calls)
