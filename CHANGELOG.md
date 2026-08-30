# Changelog

## 0.2.0 - 2026-08-30

- Add options flow so existing Notion todo entries can be edited from Home Assistant via Configure.
- Add per-entry Notion polling interval (`update_seconds`).
- Add optional default property/value for new tasks, including people/Assignee, relation, select/status, multi-select, checkbox, number, date, rich text, URL, email, and phone fields.
- Reload config entries automatically after options are changed.

## 0.1.1 - 2026-08-30

- Use Home Assistant's shared aiohttp client in config flow validation.
- Map Notion auth/setup failures to proper Home Assistant config-entry errors.
- Clear cached `todo_items` after coordinator refresh so HA state/subscribers see updated items.
- Add Home Assistant runtime harness smoke tests for config flow and todo entity cache refresh.

## 0.1.0 - 2026-08-29

- Initial public HACS integration.
- Expose filtered Notion databases as Home Assistant `todo` entities.
- Support Notion API `filter` and `sorts` JSON per config entry.
