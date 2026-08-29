"""Constants for Notion Todo List."""

from __future__ import annotations

DOMAIN = "notion_todo_list"
PLATFORMS = ["todo"]

CONF_DATABASE_ID = "database_id"
CONF_TITLE_PROPERTY = "title_property"
CONF_STATUS_PROPERTY = "status_property"
CONF_DUE_PROPERTY = "due_property"
CONF_DESCRIPTION_PROPERTY = "description_property"
CONF_FILTER_JSON = "filter_json"
CONF_SORTS_JSON = "sorts_json"
CONF_LIST_NAME = "list_name"
CONF_ACTIVE_STATUS = "active_status"
CONF_COMPLETED_STATUS = "completed_status"

DEFAULT_TITLE_PROPERTY = "Name"
DEFAULT_STATUS_PROPERTY = "Done"
DEFAULT_DUE_PROPERTY = "Due"
DEFAULT_DESCRIPTION_PROPERTY = "Description"
DEFAULT_ACTIVE_STATUS = "Not started"
DEFAULT_COMPLETED_STATUS = "Done"
NOTION_VERSION = "2022-06-28"
NOTION_API = "https://api.notion.com/v1"
