"""Small async Notion API client for database-backed todo lists."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import aiohttp

from .const import NOTION_API, NOTION_VERSION


class NotionTodoError(Exception):
    """Base Notion Todo List error."""


class NotionAuthError(NotionTodoError):
    """Notion authentication/authorization error."""


class NotionApiError(NotionTodoError):
    """Notion API request failed."""


@dataclass(slots=True)
class NotionTodoConfig:
    """Configuration for one Notion database -> HA todo list mapping."""

    token: str
    database_id: str
    title_property: str
    status_property: str
    due_property: str | None = None
    description_property: str | None = None
    filter_obj: dict[str, Any] | None = None
    sorts_obj: list[dict[str, Any]] | None = None
    active_status: str = "Not started"
    completed_status: str = "Done"
    update_seconds: int = 300
    default_property: str | None = None
    default_value: str | None = None


@dataclass(slots=True)
class NotionTodoItem:
    """Simplified Notion page mapped to a Home Assistant TodoItem."""

    uid: str
    summary: str
    completed: bool
    due: date | datetime | None = None
    description: str | None = None


class NotionClient:
    """Notion database client using HA's aiohttp session."""

    def __init__(self, session: aiohttp.ClientSession, config: NotionTodoConfig) -> None:
        self._session = session
        self.config = config
        self._status_property_type: str | None = None
        self._property_types: dict[str, str] = {}

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    async def validate(self) -> None:
        """Validate token/database access and property names."""
        database = await self._request("GET", f"/databases/{self.config.database_id}")
        properties = database.get("properties", {})
        missing = [
            name
            for name in (self.config.title_property, self.config.status_property)
            if name and name not in properties
        ]
        optional_missing = [
            name
            for name in (
                self.config.due_property,
                self.config.description_property,
                self.config.default_property,
            )
            if name and name not in properties
        ]
        if missing or optional_missing:
            raise NotionApiError(
                "Missing Notion database properties: " + ", ".join(missing + optional_missing)
            )
        self._status_property_type = properties[self.config.status_property].get("type")
        self._property_types = {
            name: str(schema.get("type") or "") for name, schema in properties.items()
        }

    async def _ensure_schema(self) -> None:
        if self._status_property_type is None:
            await self.validate()

    async def list_items(self) -> list[NotionTodoItem]:
        """Query all matching database pages and map them to todo items."""
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if self.config.filter_obj:
                body["filter"] = self.config.filter_obj
            if self.config.sorts_obj:
                body["sorts"] = self.config.sorts_obj
            if cursor:
                body["start_cursor"] = cursor
            page = await self._request(
                "POST", f"/databases/{self.config.database_id}/query", json=body
            )
            results.extend(page.get("results", []))
            if not page.get("has_more"):
                break
            cursor = page.get("next_cursor")
        return [self._page_to_item(page) for page in results if page.get("object") == "page"]

    async def create_item(
        self, summary: str, *, due: date | datetime | None = None, description: str | None = None
    ) -> None:
        """Create a page in the configured database."""
        await self._ensure_schema()
        properties: dict[str, Any] = {
            self.config.title_property: {"title": [{"type": "text", "text": {"content": summary}}]},
        }
        properties.update(self._status_property_payload(completed=False))
        if due is not None and self.config.due_property:
            properties[self.config.due_property] = {"date": {"start": due.isoformat()}}
        if description is not None and self.config.description_property:
            properties[self.config.description_property] = self._description_payload(description)
        properties.update(self._default_property_payload())
        await self._request(
            "POST",
            "/pages",
            json={"parent": {"database_id": self.config.database_id}, "properties": properties},
        )

    async def update_item(
        self,
        page_id: str,
        *,
        summary: str | None = None,
        completed: bool | None = None,
        due: date | datetime | None = None,
        description: str | None = None,
    ) -> None:
        """Update a Notion page's todo-relevant properties."""
        await self._ensure_schema()
        properties: dict[str, Any] = {}
        if summary is not None:
            properties[self.config.title_property] = {
                "title": [{"type": "text", "text": {"content": summary}}]
            }
        if completed is not None:
            properties.update(self._status_property_payload(completed=completed))
        if due is not None and self.config.due_property:
            properties[self.config.due_property] = {"date": {"start": due.isoformat()}}
        if description is not None and self.config.description_property:
            properties[self.config.description_property] = self._description_payload(description)
        if properties:
            await self._request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    async def archive_items(self, page_ids: Iterable[str]) -> None:
        """Archive pages, matching HA's delete todo operation."""
        for page_id in page_ids:
            await self._request("PATCH", f"/pages/{page_id}", json={"archived": True})

    def _page_to_item(self, page: dict[str, Any]) -> NotionTodoItem:
        props = page.get("properties", {})
        status_prop = props.get(self.config.status_property, {})
        return NotionTodoItem(
            uid=page["id"],
            summary=_plain_text(props.get(self.config.title_property, {})),
            completed=self._is_completed(status_prop),
            due=_date_value(props.get(self.config.due_property, {}))
            if self.config.due_property
            else None,
            description=_plain_text(props.get(self.config.description_property, {}))
            if self.config.description_property
            else None,
        )

    def _is_completed(self, prop: dict[str, Any]) -> bool:
        prop_type = prop.get("type")
        if prop_type == "checkbox":
            return bool(prop.get("checkbox"))
        if prop_type in {"status", "select"}:
            data = prop.get(prop_type) or {}
            value = str(data.get("name") or data.get("id") or "")
            return value.lower() == self.config.completed_status.lower()
        return False

    def _status_property_payload(self, *, completed: bool) -> dict[str, Any]:
        value = self.config.completed_status if completed else self.config.active_status
        prop_type = self._status_property_type
        if prop_type == "checkbox":
            if value.lower() in {"true", "false"}:
                checked = value.lower() == "true"
            else:
                checked = completed
            return {self.config.status_property: {"checkbox": checked}}
        if prop_type == "select":
            return {self.config.status_property: {"select": {"name": value}}}
        return {self.config.status_property: {"status": {"name": value}}}

    def _default_property_payload(self) -> dict[str, Any]:
        name = (self.config.default_property or "").strip()
        value = (self.config.default_value or "").strip()
        if not name or not value:
            return {}
        prop_type = self._property_types.get(name)
        if prop_type == "people":
            return {name: {"people": [{"id": value}]}}
        if prop_type == "relation":
            return {name: {"relation": [{"id": value}]}}
        if prop_type == "select":
            return {name: {"select": {"name": value}}}
        if prop_type == "status":
            return {name: {"status": {"name": value}}}
        if prop_type == "multi_select":
            names = [part.strip() for part in value.split(",") if part.strip()]
            return {name: {"multi_select": [{"name": part} for part in names]}}
        if prop_type == "checkbox":
            return {name: {"checkbox": value.lower() in {"1", "true", "yes", "on"}}}
        if prop_type == "number":
            try:
                number = float(value)
            except ValueError as exc:
                raise NotionApiError(f"Default value for {name} must be a number") from exc
            return {name: {"number": number}}
        if prop_type == "date":
            return {name: {"date": {"start": value}}}
        if prop_type == "rich_text":
            return {name: self._description_payload(value)}
        if prop_type == "url":
            return {name: {"url": value}}
        if prop_type == "email":
            return {name: {"email": value}}
        if prop_type == "phone_number":
            return {name: {"phone_number": value}}
        raise NotionApiError(f"Default property {name} has unsupported type: {prop_type}")

    def _description_payload(self, description: str) -> dict[str, Any]:
        return {"rich_text": [{"type": "text", "text": {"content": description}}]}

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{NOTION_API}{path}"
        try:
            async with self._session.request(method, url, headers=self.headers, json=json) as resp:
                if resp.status in {401, 403}:
                    raise NotionAuthError(await resp.text())
                if resp.status >= 400:
                    raise NotionApiError(f"Notion {resp.status}: {await resp.text()}")
                return await resp.json()
        except aiohttp.ClientError as exc:
            raise NotionApiError(str(exc)) from exc


def _plain_text(prop: dict[str, Any]) -> str:
    prop_type = prop.get("type")
    values = prop.get(prop_type) if prop_type in {"title", "rich_text"} else None
    if isinstance(values, list):
        return "".join(str(part.get("plain_text") or "") for part in values)
    if prop_type in {"status", "select"}:
        return str((prop.get(prop_type) or {}).get("name") or "")
    if prop_type == "checkbox":
        return "true" if prop.get("checkbox") else "false"
    return ""


def _date_value(prop: dict[str, Any]) -> date | datetime | None:
    if prop.get("type") != "date" or not prop.get("date"):
        return None
    raw = prop["date"].get("start")
    if not raw:
        return None
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return date.fromisoformat(raw)
    except ValueError:
        return None
