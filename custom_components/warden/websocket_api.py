"""Websocket commands behind Warden's panels."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback
import probatio as vol

from .const import (
    ALWAYS_ALLOWED_PANELS,
    DOMAIN,
    LEVELS,
    PANEL_ADMIN,
    SCOPES,
)
from .manager import LockoutError, UserStatus, WardenManager, manageable

ENTITY_RULES_SCHEMA = vol.Schema(
    {
        vol.Optional("all"): vol.Any(None, vol.In(LEVELS)),
        **{vol.Optional(scope): {str: vol.In(LEVELS)} for scope in SCOPES},
    }
)
ACCESS_LIST_SCHEMA = vol.Schema(
    {vol.Optional("all"): bool, vol.Optional("items"): [str]}
)
GROUP_FIELDS = {
    vol.Optional("description"): str,
    vol.Optional("admin"): bool,
    vol.Optional("require_mfa"): bool,
    vol.Optional("members"): [str],
    vol.Optional("entities"): ENTITY_RULES_SCHEMA,
    vol.Optional("dashboards"): ACCESS_LIST_SCHEMA,
    vol.Optional("panels"): ACCESS_LIST_SCHEMA,
}


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the commands."""
    for command in (
        ws_info,
        ws_create_group,
        ws_update_group,
        ws_delete_group,
        ws_update_settings,
        ws_me,
    ):
        websocket_api.async_register_command(hass, command)


def _manager(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> WardenManager | None:
    """Return the manager, or answer with an error if Warden isn't loaded."""
    if (manager := hass.data.get(DOMAIN)) is None:
        connection.send_error(msg["id"], "not_loaded", "Warden is not loaded")
    return manager


def _status_dict(status: UserStatus | None) -> dict[str, Any]:
    if status is None:
        return {
            "managed": False,
            "admin": False,
            "native_admin": False,
            "mfa": None,
            "mfa_deadline": None,
        }
    return {
        "managed": status.managed,
        "admin": status.admin,
        "native_admin": status.native_admin,
        "mfa": status.mfa,
        "mfa_deadline": status.mfa_deadline.isoformat()
        if status.mfa_deadline
        else None,
    }


async def _async_validate_members(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> bool:
    """Reject members that don't exist or that Warden may not manage."""
    for user_id in msg.get("members", []):
        user = await hass.auth.async_get_user(user_id)
        if user is None or not manageable(user):
            connection.send_error(
                msg["id"],
                "invalid_member",
                f"{user_id} is not a user Warden can manage (the owner and "
                "system users can't be added to groups)",
            )
            return False
    return True


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info"})
@websocket_api.async_response
async def ws_info(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return everything the admin panel shows."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    users = []
    for user in await hass.auth.async_get_users():
        if user.system_generated:
            continue
        users.append(
            {
                "id": user.id,
                "name": user.name,
                "is_owner": user.is_owner,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "mfa_modules": list(await hass.auth.async_get_enabled_mfa(user)),
                **_status_dict(manager.status.get(user.id)),
            }
        )

    dashboards, panels = [], []
    for key, panel in hass.data.get(DATA_PANELS, {}).items():
        entry = {"url_path": key, "title": panel.sidebar_title or key}
        if panel.component_name == "lovelace":
            dashboards.append(entry)
        elif (
            not panel.require_admin
            and key not in ALWAYS_ALLOWED_PANELS
            and key != PANEL_ADMIN
        ):
            panels.append(entry)

    connection.send_result(
        msg["id"],
        {
            "groups": [group.to_dict() for group in manager.store.groups.values()],
            "settings": {
                "require_mfa_all": manager.store.settings.require_mfa_all,
                "mfa_grace_days": manager.store.settings.mfa_grace_days,
            },
            "users": users,
            "dashboards": dashboards,
            "panels": panels,
            "mfa_modules": [
                {"id": module.id, "name": module.name}
                for module in hass.auth.auth_mfa_modules
            ],
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/group/create",
        vol.Required("name"): vol.All(str, vol.Length(min=1)),
        **GROUP_FIELDS,
    }
)
@websocket_api.async_response
async def ws_create_group(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Create a group."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if not await _async_validate_members(hass, connection, msg):
        return
    data = {k: v for k, v in msg.items() if k not in ("id", "type")}
    try:
        group = await manager.async_create_group(data, connection.user)
    except LockoutError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(msg["id"], group.to_dict())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/group/update",
        vol.Required("group_id"): str,
        vol.Optional("name"): vol.All(str, vol.Length(min=1)),
        **GROUP_FIELDS,
    }
)
@websocket_api.async_response
async def ws_update_group(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Update a group."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if msg["group_id"] not in manager.store.groups:
        connection.send_error(msg["id"], "not_found", "Group not found")
        return
    if not await _async_validate_members(hass, connection, msg):
        return
    data = {k: v for k, v in msg.items() if k not in ("id", "type", "group_id")}
    try:
        group = await manager.async_update_group(msg["group_id"], data, connection.user)
    except LockoutError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(msg["id"], group.to_dict())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/group/delete", vol.Required("group_id"): str}
)
@websocket_api.async_response
async def ws_delete_group(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete a group."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    if msg["group_id"] not in manager.store.groups:
        connection.send_error(msg["id"], "not_found", "Group not found")
        return
    try:
        await manager.async_delete_group(msg["group_id"], connection.user)
    except LockoutError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/settings/update",
        vol.Optional("require_mfa_all"): bool,
        vol.Optional("mfa_grace_days"): vol.All(int, vol.Range(min=0, max=365)),
    }
)
@websocket_api.async_response
async def ws_update_settings(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Change global settings."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    try:
        settings = await manager.async_update_settings(msg, connection.user)
    except LockoutError as err:
        connection.send_error(msg["id"], err.code, str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "require_mfa_all": settings.require_mfa_all,
            "mfa_grace_days": settings.mfa_grace_days,
        },
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/me"})
@websocket_api.async_response
async def ws_me(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the current user's own Warden status."""
    if (manager := _manager(hass, connection, msg)) is None:
        return
    user = connection.user
    groups = manager.store.groups_for_user(user.id)
    connection.send_result(
        msg["id"],
        {
            **_status_dict(manager.status.get(user.id)),
            "groups": [group.name for group in groups],
            "mfa_modules": list(await hass.auth.async_get_enabled_mfa(user)),
        },
    )
