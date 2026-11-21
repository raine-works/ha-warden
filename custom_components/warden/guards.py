"""Enforce dashboard and panel access for Warden-managed users.

Home Assistant only knows "admin" or "everyone" for dashboards and panels, so
Warden wraps the two websocket commands the frontend uses for them:

* ``get_panels`` lists the sidebar. Panels a user may not open are removed, so
  the frontend has no route to them.
* ``lovelace/config`` returns a dashboard's content. For a dashboard a user may
  not open, a placeholder explaining why is returned instead, so a hidden
  dashboard can't be read by asking for it directly.
* ``frontend/get_system_data`` and ``frontend/subscribe_system_data`` give the
  frontend the default dashboard (key ``core``). When a user may not open it,
  they're given their first allowed dashboard instead: the frontend falls back
  from the default to the ``home`` panel to ``notfound``, and with none of them
  in a restricted user's sidebar it crashed on every render, stuck on its
  loading screen.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from .const import (
    ALWAYS_ALLOWED_PANELS,
    DEFAULT_DASHBOARD,
    LOGGER,
    MFA_RESTRICTED,
    PANEL_SECURITY,
)
from .manager import WardenManager
from .models import UiAccess

GET_PANELS = "get_panels"
LOVELACE_CONFIG = "lovelace/config"
GET_SYSTEM_DATA = "frontend/get_system_data"
SUBSCRIBE_SYSTEM_DATA = "frontend/subscribe_system_data"
SYSTEM_DATA_CORE = "core"
DEFAULT_PANEL_KEY = "default_panel"

type Handler = Callable[[HomeAssistant, ActiveConnection, dict[str, Any]], Any]


class _ResultCapture:
    """Stands in for a connection to catch a handler's result message."""

    def __init__(self, connection: ActiveConnection) -> None:
        self._connection = connection
        self.messages: list[Any] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def send_message(self, message: Any) -> None:
        self.messages.append(message)


class Guards:
    """Installs and removes the websocket command wrappers."""

    def __init__(self, hass: HomeAssistant, manager: WardenManager) -> None:
        """Initialize the guards."""
        self._hass = hass
        self._manager = manager
        self._originals: dict[str, tuple[Handler, Any]] = {}

    @callback
    def async_install(self) -> None:
        """Wrap the commands. Live connections share the handler table."""
        handlers = self._hass.data[websocket_api.DOMAIN]
        for command, wrap in (
            (GET_PANELS, self._wrap_get_panels),
            (LOVELACE_CONFIG, self._wrap_lovelace_config),
            (GET_SYSTEM_DATA, self._wrap_system_data),
            (SUBSCRIBE_SYSTEM_DATA, self._wrap_system_data),
        ):
            if command not in handlers:
                LOGGER.warning("Can't guard %s: command not registered", command)
                continue
            handler, schema = handlers[command]
            self._originals[command] = (handler, schema)
            handlers[command] = (wrap(handler), schema)

    @callback
    def async_remove(self) -> None:
        """Put the original commands back."""
        handlers = self._hass.data[websocket_api.DOMAIN]
        for command, original in self._originals.items():
            handlers[command] = original
        self._originals.clear()

    def _wrap_get_panels(self, original: Handler) -> Handler:
        manager = self._manager

        @callback
        def get_panels(
            hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
        ) -> None:
            user = connection.user
            access = manager.ui_access(user)
            show_security = manager.needs_mfa_attention(user)
            if access is None and show_security:
                original(hass, connection, msg)
                return

            capture = _ResultCapture(connection)
            original(hass, capture, msg)  # type: ignore[arg-type]
            for message in capture.messages:
                if isinstance(message, dict) and message.get("success"):
                    message["result"] = {
                        key: panel
                        for key, panel in message["result"].items()
                        if _panel_allowed(key, panel, access, show_security)
                    }
                connection.send_message(message)

        return get_panels

    def _wrap_system_data(self, original: Handler) -> Handler:
        manager = self._manager

        @callback
        def system_data(
            hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
        ) -> Any:
            user = connection.user
            access = manager.ui_access(user)
            if access is None or msg.get("key") != SYSTEM_DATA_CORE:
                return original(hass, connection, msg)
            show_security = manager.needs_mfa_attention(user)

            def rewrite(payload: Any) -> Any:
                value = payload.get("value") if isinstance(payload, dict) else None
                if not isinstance(value, dict) or DEFAULT_PANEL_KEY not in value:
                    return payload
                fallback = fallback_default_panel(
                    hass, access, show_security, value[DEFAULT_PANEL_KEY]
                )
                if fallback == value[DEFAULT_PANEL_KEY]:
                    return payload
                value = {k: v for k, v in value.items() if k != DEFAULT_PANEL_KEY}
                if fallback is not None:
                    value[DEFAULT_PANEL_KEY] = fallback
                return {**payload, "value": value}

            return original(
                hass,
                _DefaultPanelRewriter(connection, rewrite),  # type: ignore[arg-type]
                msg,
            )

        return system_data

    def _wrap_lovelace_config(self, original: Handler) -> Handler:
        manager = self._manager

        @callback
        def lovelace_config(
            hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
        ) -> None:
            user = connection.user
            access = manager.ui_access(user)
            url_path = msg.get("url_path") or DEFAULT_DASHBOARD
            if access is None or access.allows_dashboard(url_path):
                original(hass, connection, msg)
                return
            status = manager.status.get(user.id)
            restricted = status is not None and status.mfa == MFA_RESTRICTED
            connection.send_result(
                msg["id"], _placeholder(hass, access, restricted=restricted)
            )

        return lovelace_config


class _DefaultPanelRewriter:
    """Stands in for a connection, giving a restricted user a default they may open.

    It stays the connection a subscription answers on, so every later update is
    rewritten too.
    """

    def __init__(
        self, connection: ActiveConnection, rewrite: Callable[[Any], Any]
    ) -> None:
        self._connection = connection
        self._rewrite = rewrite

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def send_result(self, msg_id: int, result: Any | None = None) -> None:
        self._connection.send_result(msg_id, self._rewrite(result))

    def send_event(self, msg_id: int, event: Any | None = None) -> None:
        self._connection.send_event(msg_id, self._rewrite(event))


def fallback_default_panel(
    hass: HomeAssistant, access: UiAccess, show_security: bool, current: Any
) -> str | None:
    """The default dashboard for a restricted user: the system's when they may
    open it, else their first allowed dashboard (None: leave it unset)."""
    panels = hass.data.get(DATA_PANELS, {})

    def allowed(url_path: Any) -> bool:
        panel = panels.get(url_path) if isinstance(url_path, str) else None
        return panel is not None and _panel_allowed(
            url_path,
            {"component_name": panel.component_name},
            access,
            show_security,
        )

    if allowed(current):
        return current
    for url_path in access.dashboards.items:
        if allowed(url_path):
            return url_path
    return None


def _panel_allowed(
    key: str, panel: dict[str, Any], access: UiAccess | None, show_security: bool
) -> bool:
    if key == PANEL_SECURITY:
        return show_security
    if access is None or key in ALWAYS_ALLOWED_PANELS:
        return True
    if panel.get("component_name") == "lovelace":
        # Keep the default dashboard in the sidebar; its content is replaced
        # with a placeholder if denied, which is friendlier than a dead link.
        return key == DEFAULT_DASHBOARD or access.allows_dashboard(key)
    return access.allows_panel(key)


def _placeholder(
    hass: HomeAssistant, access: UiAccess, *, restricted: bool
) -> dict[str, Any]:
    """Return a dashboard config explaining why access was denied."""
    if restricted:
        content = (
            "## Two-factor authentication required\n\n"
            "Your account must use two-factor authentication before you can "
            "use Home Assistant.\n\n"
            "[Set it up on your security page](/profile/security), then reload."
        )
    else:
        allowed = [
            (key, panel.sidebar_title or key)
            for key, panel in hass.data.get(DATA_PANELS, {}).items()
            if panel.component_name == "lovelace"
            and key != DEFAULT_DASHBOARD
            and access.allows_dashboard(key)
        ]
        content = "## No access\n\nYou don't have access to this dashboard."
        if allowed:
            links = "\n".join(f"- [{title}](/{key})" for key, title in allowed)
            content += f"\n\nDashboards you can open:\n\n{links}"
    return {
        "title": "Home",
        "views": [
            {
                "title": "Home",
                "path": "home",
                "cards": [{"type": "markdown", "content": content}],
            }
        ],
    }
