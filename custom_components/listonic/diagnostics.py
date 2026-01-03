"""Diagnostics support for Listonic."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ListonicConfigEntry
from .const import CONF_EMAIL, CONF_PASSWORD, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ListonicConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    # Build list info without exposing item names (privacy)
    lists_info = []
    if coordinator.data:
        for list_id, listonic_list in coordinator.data.items():
            lists_info.append(
                {
                    "list_id": list_id,
                    "item_count": len(listonic_list.items),
                    "checked_count": listonic_list.checked_count,
                    "unchecked_count": listonic_list.unchecked_count,
                    "is_archived": listonic_list.is_archived,
                }
            )

    return {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "lists": {
            "count": len(coordinator.data) if coordinator.data else 0,
            "details": lists_info,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_time": (
                coordinator.last_update_success_time.isoformat()
                if coordinator.last_update_success_time
                else None
            ),
            "update_interval_seconds": entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            ),
        },
        "authentication": {
            "has_token": coordinator.client._token is not None,
            "has_refresh_token": coordinator.client._refresh_token is not None,
        },
    }
