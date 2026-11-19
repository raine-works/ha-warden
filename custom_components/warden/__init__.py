"""Warden: groups, fine-grained permissions and required 2FA for users."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.loader import async_get_integration

from . import websocket_api
from .auth_bridge import IncompatibleAuthStore
from .const import (
    DOMAIN,
    PANEL_ADMIN,
    PANEL_COMPONENT,
    PANEL_SECURITY,
    STATIC_URL,
)
from .guards import Guards
from .manager import WardenManager
from .store import WardenStore

type WardenConfigEntry = ConfigEntry[WardenManager]

_STATIC_REGISTERED = f"{DOMAIN}_static_registered"


async def async_setup_entry(hass: HomeAssistant, entry: WardenConfigEntry) -> bool:
    """Set up Warden."""
    store = WardenStore(hass)
    await store.async_load()
    try:
        manager = WardenManager(hass, store)
    except IncompatibleAuthStore as err:
        raise ConfigEntryError(str(err)) from err

    entry.runtime_data = manager
    hass.data[DOMAIN] = manager
    websocket_api.async_register(hass)
    await _async_register_panels(hass)

    guards = Guards(hass, manager)
    guards.async_install()
    entry.async_on_unload(guards.async_remove)
    entry.async_on_unload(manager.async_stop)

    await manager.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WardenConfigEntry) -> bool:
    """Unload Warden.

    Users keep the groups and policies Warden gave them, so unloading or
    restarting never widens anyone's access. Removing the integration is what
    hands users back their original groups.
    """
    for panel in (PANEL_ADMIN, PANEL_SECURITY):
        frontend.async_remove_panel(hass, panel, warn_if_unknown=False)
    hass.data.pop(DOMAIN, None)
    # Flush pending changes; removal reads them back from disk.
    await entry.runtime_data.store.async_save()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: WardenConfigEntry) -> None:
    """Give every user their original groups back and delete Warden's data."""
    store = WardenStore(hass)
    await store.async_load()
    await WardenManager(hass, store).async_release_all()
    await store.async_remove()


async def _async_register_panels(hass: HomeAssistant) -> None:
    integration = await async_get_integration(hass, DOMAIN)
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    STATIC_URL, str(Path(__file__).parent / "frontend"), False
                )
            ]
        )
        hass.data[_STATIC_REGISTERED] = True

    module_url = f"{STATIC_URL}/warden-panel.js?v={integration.version}"
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_ADMIN,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="Warden",
        sidebar_icon="mdi:shield-account",
        module_url=module_url,
        require_admin=True,
        config={"mode": "admin"},
    )
    # Shown only to users who still have to set up 2FA (see guards.py).
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_SECURITY,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="Account security",
        sidebar_icon="mdi:shield-lock",
        module_url=module_url,
        require_admin=False,
        config={"mode": "security"},
    )
