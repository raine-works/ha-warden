"""End-to-end tests: users, groups, guards and required 2FA."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.auth.auth_store import AuthStore
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.auth.models import Group as AuthGroup
from homeassistant.components import frontend
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.const import EVENT_PANELS_UPDATED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    entity_registry as er,
    issue_registry as ir,
    label_registry as lr,
)
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.warden.const import (
    DOMAIN,
    PANEL_SECURITY,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from custom_components.warden.manager import WardenManager

from .conftest import ws_call


def group_ids(user: Any) -> list[str]:
    return [group.id for group in user.groups]


async def create_group(hass: HomeAssistant, hass_ws_client: Any, **fields: Any) -> dict:
    client = await hass_ws_client(hass)
    group = await ws_call(client, type="warden/group/create", **fields)
    await hass.async_block_till_done()
    return group


async def test_group_membership_applies_policy(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Joining a group swaps the user's groups for a compiled policy."""
    kid = await make_user()
    hass.states.async_set("light.den", "on")
    hass.states.async_set("lock.front", "locked")
    assert kid.permissions.check_entity("lock.front", "control")

    group = await create_group(
        hass,
        hass_ws_client,
        name="Kids",
        members=[kid.id],
        entities={"domains": {"light": "control"}},
    )
    assert group_ids(kid) == [f"warden-{kid.id}"]
    assert not kid.is_admin
    assert kid.permissions.check_entity("light.den", "control")
    assert not kid.permissions.check_entity("lock.front", "read")

    # Narrowing the group narrows the user right away.
    client = await hass_ws_client(hass)
    await ws_call(
        client,
        type="warden/group/update",
        group_id=group["id"],
        entities={"domains": {"light": "read"}},
    )
    assert kid.permissions.check_entity("light.den", "read")
    assert not kid.permissions.check_entity("light.den", "control")

    # The custom group is saved with the auth data, so it survives restarts.
    saved = hass.auth._store._data_to_save()
    assert any(g["id"] == f"warden-{kid.id}" and "policy" in g for g in saved["groups"])


async def test_leaving_all_groups_restores_original_groups(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """A user no longer in any group gets their old groups back."""
    kid = await make_user()
    group = await create_group(hass, hass_ws_client, name="Kids", members=[kid.id])
    assert group_ids(kid) == [f"warden-{kid.id}"]

    client = await hass_ws_client(hass)
    await ws_call(client, type="warden/group/delete", group_id=group["id"])
    await hass.async_block_till_done()
    assert group_ids(kid) == [GROUP_ID_USER]
    assert f"warden-{kid.id}" not in hass.auth._store._groups


async def test_admin_group(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Members of an admin group become Home Assistant administrators."""
    user = await make_user("Parent")
    await create_group(
        hass, hass_ws_client, name="Parents", admin=True, members=[user.id]
    )
    assert group_ids(user) == [GROUP_ID_ADMIN]
    assert user.is_admin


async def test_external_group_change_is_reverted(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Changing a managed user's groups elsewhere doesn't escape Warden."""
    kid = await make_user()
    await create_group(hass, hass_ws_client, name="Kids", members=[kid.id])

    await hass.auth.async_update_user(kid, group_ids=[GROUP_ID_USER])
    await hass.async_block_till_done()
    assert group_ids(kid) == [f"warden-{kid.id}"]


async def test_native_admin_overrides_group_rules(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """A Home Assistant administrator keeps full access in any group."""
    hass.states.async_set("lock.front", "locked")
    admin = await make_user("Admin", [GROUP_ID_ADMIN])
    group = await create_group(
        hass,
        hass_ws_client,
        name="Kids",
        members=[admin.id],
        entities={"domains": {"light": "read"}},
        dashboards={"items": []},
        panels={"items": []},
    )
    assert group_ids(admin) == [GROUP_ID_ADMIN]
    assert admin.is_admin
    assert admin.permissions.check_entity("lock.front", "control")
    assert warden.ui_access(admin) is None
    assert warden.status[admin.id].native_admin

    # Turning off Administrator under Settings → People applies the rules...
    await hass.auth.async_update_user(admin, group_ids=[GROUP_ID_USER])
    await hass.async_block_till_done()
    assert group_ids(admin) == [f"warden-{admin.id}"]
    assert not admin.permissions.check_entity("lock.front", "read")

    # ...and turning it back on lifts them again.
    await hass.auth.async_update_user(admin, group_ids=[GROUP_ID_ADMIN])
    await hass.async_block_till_done()
    assert group_ids(admin) == [GROUP_ID_ADMIN]
    assert admin.permissions.check_entity("lock.front", "control")

    # Leaving the group changes nothing for them.
    client = await hass_ws_client(hass)
    await ws_call(client, type="warden/group/update", group_id=group["id"], members=[])
    await hass.async_block_till_done()
    assert group_ids(admin) == [GROUP_ID_ADMIN]


async def test_admin_demoted_by_older_version_is_restored(
    hass: HomeAssistant, hass_owner_user: Any, hass_storage: dict, make_user: Any
) -> None:
    """Admins that 0.1.1 put on a group policy get admin back on upgrade."""
    admin = await make_user("Admin", [GROUP_ID_ADMIN])
    hass.auth._store._groups[f"warden-{admin.id}"] = AuthGroup(
        id=f"warden-{admin.id}", name="Warden: Admin", policy={"entities": {}}
    )
    await hass.auth.async_update_user(admin, group_ids=[f"warden-{admin.id}"])
    assert not admin.is_admin
    hass_storage[STORAGE_KEY] = {
        "version": STORAGE_VERSION,
        "key": STORAGE_KEY,
        "data": {
            "groups": [{"id": "g", "name": "Kids", "members": [admin.id]}],
            "users": {admin.id: {"original_group_ids": [GROUP_ID_ADMIN]}},
        },
    }
    entry = MockConfigEntry(domain=DOMAIN, title="Warden")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert group_ids(admin) == [GROUP_ID_ADMIN]
    assert f"warden-{admin.id}" not in hass.auth._store._groups


async def test_admin_cannot_remove_own_admin_access(
    hass: HomeAssistant,
    warden: WardenManager,
    hass_ws_client: Any,
    make_user: Any,
    user_ws: Any,
) -> None:
    """An admin whose role comes from a Warden group can't revoke it."""
    parent = await make_user("Parent")
    group = await create_group(
        hass, hass_ws_client, name="Parents", admin=True, members=[parent.id]
    )
    assert parent.is_admin
    client = await user_ws(parent)
    for msg in (
        {"type": "warden/group/update", "group_id": group["id"], "members": []},
        {"type": "warden/group/update", "group_id": group["id"], "admin": False},
        {"type": "warden/group/delete", "group_id": group["id"]},
    ):
        await client.send_json_auto_id(msg)
        response = await client.receive_json()
        assert response["error"]["code"] == "lose_admin", msg
    await hass.async_block_till_done()
    assert parent.is_admin
    assert group["id"] in warden.store.groups

    # Another admin can still make the change.
    other = await hass_ws_client(hass)
    await ws_call(other, type="warden/group/delete", group_id=group["id"])
    await hass.async_block_till_done()
    assert not parent.is_admin


async def test_admin_cannot_require_2fa_they_lack_without_grace(
    hass: HomeAssistant,
    mfa_module: str,
    warden: WardenManager,
    hass_ws_client: Any,
    hass_admin_user: Any,
) -> None:
    """Requiring 2FA with no grace period can't lock out the admin doing it."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "warden/settings/update", "require_mfa_all": True, "mfa_grace_days": 0}
    )
    response = await client.receive_json()
    assert response["error"]["code"] == "requires_your_mfa"
    assert not warden.store.settings.require_mfa_all

    # With a grace period they have time to enroll, so it's allowed.
    await ws_call(
        client, type="warden/settings/update", require_mfa_all=True, mfa_grace_days=7
    )
    await hass.async_block_till_done()
    assert warden.status[hass_admin_user.id].mfa == "grace"
    assert hass_admin_user.is_admin


async def test_admin_missing_2fa_is_restricted_then_restored(
    hass: HomeAssistant,
    mfa_module: str,
    warden: WardenManager,
    hass_ws_client: Any,
    make_user: Any,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Required 2FA applies to admins; enrolling gives admin straight back."""
    admin = await make_user("Admin", [GROUP_ID_ADMIN])
    await create_group(
        hass, hass_ws_client, name="IT", members=[admin.id], require_mfa=True
    )
    assert admin.is_admin

    freezer.tick(timedelta(days=8))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert warden.status[admin.id].mfa == "restricted"
    assert not admin.is_admin

    await hass.auth.get_auth_mfa_module(mfa_module).async_setup_user(
        admin.id, {"pin": "123456"}
    )
    await hass.async_block_till_done()
    assert group_ids(admin) == [GROUP_ID_ADMIN]


async def test_owner_cannot_be_added(
    hass: HomeAssistant,
    warden: WardenManager,
    hass_ws_client: Any,
    hass_owner_user: Any,
) -> None:
    """The owner can't be managed, so nobody can lock everyone out."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "warden/group/create", "name": "X", "members": [hass_owner_user.id]}
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "invalid_member"


async def test_admin_commands_require_admin(
    hass: HomeAssistant, warden: WardenManager, make_user: Any, user_ws: Any
) -> None:
    """Regular users can't change Warden's configuration."""
    client = await user_ws(await make_user())
    await client.send_json_auto_id({"type": "warden/info"})
    response = await client.receive_json()
    assert response["error"]["code"] == "unauthorized"


async def test_dashboard_and_panel_guards(
    hass: HomeAssistant,
    warden: WardenManager,
    hass_ws_client: Any,
    make_user: Any,
    user_ws: Any,
) -> None:
    """Managed users see only the dashboards and panels their groups allow."""
    admin = await hass_ws_client(hass)
    for url_path in ("dashboard-kids", "dashboard-secret"):
        await ws_call(
            admin,
            type="lovelace/dashboards/create",
            url_path=url_path,
            title=url_path,
        )
    kid = await make_user()
    await create_group(
        hass,
        hass_ws_client,
        name="Kids",
        members=[kid.id],
        dashboards={"items": ["dashboard-kids"]},
        panels={"items": ["allowed-panel"]},
    )
    for panel in ("allowed-panel", "other-panel"):
        frontend.async_register_built_in_panel(
            hass, "iframe", panel, frontend_url_path=panel
        )

    client = await user_ws(kid)
    panels = await ws_call(client, type="get_panels")
    assert "dashboard-kids" in panels
    assert "dashboard-secret" not in panels
    assert "lovelace" in panels  # kept, but its content is replaced
    assert "profile" in panels
    assert "allowed-panel" in panels
    assert "other-panel" not in panels
    assert PANEL_SECURITY not in panels

    await client.send_json_auto_id(
        {"type": "lovelace/config", "url_path": "dashboard-secret"}
    )
    response = await client.receive_json()
    assert response["success"]
    assert "No access" in response["result"]["views"][0]["cards"][0]["content"]
    assert "dashboard-kids" in response["result"]["views"][0]["cards"][0]["content"]

    # Allowed dashboards load normally (this one is empty, so "not found").
    await client.send_json_auto_id(
        {"type": "lovelace/config", "url_path": "dashboard-kids"}
    )
    response = await client.receive_json()
    assert response["error"]["code"] == "config_not_found"

    # Unmanaged users and admins are untouched.
    admin_panels = await ws_call(admin, type="get_panels")
    assert "dashboard-secret" in admin_panels
    assert PANEL_SECURITY not in admin_panels


async def test_restricted_user_always_has_a_landing_page(
    hass: HomeAssistant,
    warden: WardenManager,
    hass_ws_client: Any,
    make_user: Any,
    user_ws: Any,
) -> None:
    """A group allowing one dashboard and no panels, while the system default is a
    dashboard it can't open (the wall panels' case): the frontend fell back to the
    home panel, then notfound, found neither, and crashed on every render. The
    user's default becomes their first allowed dashboard, and notfound stays."""
    admin = await hass_ws_client(hass)
    for url_path in ("dashboard-kitchen", "dashboard-family"):
        await ws_call(
            admin, type="lovelace/dashboards/create", url_path=url_path, title=url_path
        )
    await ws_call(
        admin,
        type="frontend/set_system_data",
        key="core",
        value={"default_panel": "dashboard-family", "onboarded_version": "1"},
    )
    panel = await make_user()
    await create_group(
        hass,
        hass_ws_client,
        name="Wall Panels",
        members=[panel.id],
        dashboards={"items": ["dashboard-kitchen"]},
    )

    client = await user_ws(panel)
    panels = await ws_call(client, type="get_panels")
    assert "dashboard-kitchen" in panels
    assert "dashboard-family" not in panels
    assert "notfound" in panels

    data = await ws_call(client, type="frontend/get_system_data", key="core")
    assert data["value"] == {
        "default_panel": "dashboard-kitchen",
        "onboarded_version": "1",
    }

    await client.send_json_auto_id(
        {"type": "frontend/subscribe_system_data", "key": "core"}
    )
    event = await client.receive_json()
    assert event["event"]["value"]["default_panel"] == "dashboard-kitchen"
    assert (await client.receive_json())["success"]

    # Later changes are rewritten on the same subscription
    await ws_call(
        admin,
        type="frontend/set_system_data",
        key="core",
        value={"default_panel": "dashboard-kitchen"},
    )
    event = await client.receive_json()
    assert event["event"]["value"]["default_panel"] == "dashboard-kitchen"

    # Admins see the system's own default
    data = await ws_call(admin, type="frontend/get_system_data", key="core")
    assert data["value"]["default_panel"] == "dashboard-kitchen"
    await ws_call(
        admin,
        type="frontend/set_system_data",
        key="core",
        value={"default_panel": "dashboard-family"},
    )
    data = await ws_call(admin, type="frontend/get_system_data", key="core")
    assert data["value"]["default_panel"] == "dashboard-family"


async def test_mfa_grace_then_restriction(
    hass: HomeAssistant,
    mfa_module: str,
    warden: WardenManager,
    hass_ws_client: Any,
    make_user: Any,
    user_ws: Any,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Users get a grace period, are then restricted until they enroll."""
    hass.states.async_set("light.den", "on")
    kid = await make_user()
    await create_group(
        hass,
        hass_ws_client,
        name="Kids",
        members=[kid.id],
        require_mfa=True,
        entities={"all": "control"},
        dashboards={"all": True},
    )
    assert warden.status[kid.id].mfa == "grace"
    assert kid.permissions.check_entity("light.den", "control")
    client = await user_ws(kid)
    assert PANEL_SECURITY in await ws_call(client, type="get_panels")
    me = await ws_call(client, type="warden/me")
    assert me["mfa"] == "grace" and me["mfa_deadline"]

    freezer.tick(timedelta(days=8))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert warden.status[kid.id].mfa == "restricted"
    assert not kid.permissions.check_entity("light.den", "read")
    await client.send_json_auto_id({"type": "lovelace/config"})
    response = await client.receive_json()
    assert "Two-factor" in response["result"]["views"][0]["cards"][0]["content"]

    # Enrolling lifts the restriction at once. The profile page's setup flow
    # calls the module directly, so that's what the test does too.
    module = hass.auth.get_auth_mfa_module(mfa_module)
    await module.async_setup_user(kid.id, {"pin": "123456"})
    await hass.async_block_till_done()
    assert warden.status[kid.id].mfa == "compliant"
    assert kid.permissions.check_entity("light.den", "control")
    assert PANEL_SECURITY not in await ws_call(client, type="get_panels")

    # Turning 2FA off again gets no second grace period.
    await hass.auth.async_disable_user_mfa(kid, mfa_module)
    await hass.async_block_till_done()
    assert warden.status[kid.id].mfa == "restricted"


async def test_require_mfa_for_everyone(
    hass: HomeAssistant,
    mfa_module: str,
    warden: WardenManager,
    hass_ws_client: Any,
    hass_owner_user: Any,
    hass_admin_user: Any,
    make_user: Any,
) -> None:
    """The global setting covers ungrouped users, and spares the owner."""
    hass.states.async_set("light.den", "on")
    user = await make_user("Guest")
    # The admin making the change must have 2FA, or they'd lock themselves out.
    await hass.auth.get_auth_mfa_module(mfa_module).async_setup_user(
        hass_admin_user.id, {"pin": "123456"}
    )
    client = await hass_ws_client(hass)
    await ws_call(
        client, type="warden/settings/update", require_mfa_all=True, mfa_grace_days=0
    )
    await hass.async_block_till_done()
    assert warden.status[user.id].mfa == "restricted"
    assert not user.permissions.check_entity("light.den", "read")
    assert hass_owner_user.id not in warden.status

    await hass.auth.get_auth_mfa_module(mfa_module).async_setup_user(
        user.id, {"pin": "123456"}
    )
    await hass.async_block_till_done()
    # Not in any group, so they simply get their own groups back.
    assert group_ids(user) == [GROUP_ID_USER]
    assert user.permissions.check_entity("light.den", "control")


async def test_mfa_required_without_module_raises_repair(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """With no 2FA module loaded, nobody is restricted and a repair appears."""
    user = await make_user()
    client = await hass_ws_client(hass)
    await ws_call(
        client, type="warden/settings/update", require_mfa_all=True, mfa_grace_days=0
    )
    await hass.async_block_till_done()
    assert warden.status[user.id].mfa == "unenforceable"
    assert group_ids(user) == [GROUP_ID_USER]
    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_mfa_module")


async def test_deny_rule_tracks_new_entities(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Policies expanded for a deny pick up entities added later."""
    hass.states.async_set("light.den", "on")
    kid = await make_user()
    await create_group(
        hass,
        hass_ws_client,
        name="Kids",
        members=[kid.id],
        entities={"all": "control", "domains": {"lock": "deny"}},
    )
    hass.states.async_set("switch.new", "off")
    hass.states.async_set("lock.new", "locked")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, fire_all=True)
    await hass.async_block_till_done()
    assert kid.permissions.check_entity("switch.new", "control")
    assert not kid.permissions.check_entity("lock.new", "read")


async def test_remove_entry_releases_everyone(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Removing Warden hands users back their original groups."""
    kid = await make_user()
    await create_group(hass, hass_ws_client, name="Kids", members=[kid.id])
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert group_ids(kid) == [GROUP_ID_USER]
    assert not any(g.startswith("warden-") for g in hass.auth._store._groups)


async def test_unload_keeps_restrictions(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Unloading never widens access; reloading picks up where it left off."""
    kid = await make_user()
    await create_group(hass, hass_ws_client, name="Kids", members=[kid.id])
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    assert group_ids(kid) == [f"warden-{kid.id}"]
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert group_ids(kid) == [f"warden-{kid.id}"]


async def test_auth_data_reloads_after_restart(
    hass: HomeAssistant,
    warden: WardenManager,
    hass_ws_client: Any,
    make_user: Any,
    hass_storage: dict[str, Any],
) -> None:
    """Saved auth data with Warden's groups loads cleanly on the next start."""
    hass.states.async_set("light.den", "on")
    kid = await make_user()
    await create_group(
        hass,
        hass_ws_client,
        name="Kids",
        members=[kid.id],
        entities={"domains": {"light": "read"}},
    )
    hass_storage["auth"] = {
        "version": 1,
        "minor_version": 1,
        "key": "auth",
        "data": hass.auth._store._data_to_save(),
    }
    store = AuthStore(hass)
    await store.async_load()
    reloaded = await store.async_get_user(kid.id)
    assert group_ids(reloaded) == [f"warden-{kid.id}"]
    assert reloaded.permissions.check_entity("light.den", "read")
    assert not reloaded.permissions.check_entity("light.den", "control")


async def test_logged_in_user_is_prompted_and_can_enroll(
    hass: HomeAssistant,
    mfa_module: str,
    warden: WardenManager,
    hass_ws_client: Any,
    make_user: Any,
    user_ws: Any,
) -> None:
    """An open session hears 2FA become required, and can set it up there."""
    kid = await make_user()
    client = await user_ws(kid)
    await client.send_json_auto_id({"type": "warden/me/subscribe"})
    sub_id = (await client.receive_json())["id"]
    first = await client.receive_json()
    assert first["id"] == sub_id
    assert first["event"]["mfa"] == "exempt"
    assert first["event"]["available_mfa_modules"] == [
        {"id": mfa_module, "name": "Insecure Personal Identify Number"}
    ]

    sidebar_refreshes = async_capture_events(hass, EVENT_PANELS_UPDATED)
    await create_group(
        hass, hass_ws_client, name="Kids", members=[kid.id], require_mfa=True
    )
    event = (await client.receive_json())["event"]
    assert event["mfa"] == "grace"
    assert event["mfa_deadline"]
    # Open frontends refetch the sidebar, which now has Account security.
    assert sidebar_refreshes

    # The prompt runs Home Assistant's own setup flow over the same socket.
    await client.send_json_auto_id(
        {"type": "auth/setup_mfa", "mfa_module_id": mfa_module}
    )
    form = await client.receive_json()
    assert form["result"]["type"] == "form"
    await client.send_json_auto_id(
        {
            "type": "auth/setup_mfa",
            "flow_id": form["result"]["flow_id"],
            "user_input": {"pin": "123456"},
        }
    )
    # Enrolling pushes the new status, possibly before the flow's own result.
    messages = [await client.receive_json(), await client.receive_json()]
    result = next(m for m in messages if m.get("type") == "result")
    pushed = next(m for m in messages if m.get("type") == "event")
    assert result["result"]["type"] == "create_entry"
    assert pushed["event"]["mfa"] == "compliant"
    assert pushed["event"]["mfa_modules"] == [mfa_module]


async def test_prompt_script_loads_on_every_page(
    hass: HomeAssistant, warden: WardenManager
) -> None:
    """The prompt is registered as an extra frontend module while loaded."""
    urls = hass.data[DATA_EXTRA_MODULE_URL].urls
    assert any("/warden_static/warden-prompt.js" in url for url in urls)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    urls = hass.data[DATA_EXTRA_MODULE_URL].urls
    assert not any("warden-prompt.js" in url for url in urls)


async def test_label_rule_follows_label_changes(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Labeling or unlabeling an entity changes access without a save."""
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create("light", "test", "den", suggested_object_id="den")
    hass.states.async_set("light.den", "on")
    kids = lr.async_get(hass).async_create("Kids").label_id
    kid = await make_user()
    await create_group(
        hass,
        hass_ws_client,
        name="Kids",
        members=[kid.id],
        entities={"label_ids": {kids: "control"}},
    )
    assert not kid.permissions.check_entity("light.den", "read")

    ent_reg.async_update_entity("light.den", labels={kids})
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()
    assert kid.permissions.check_entity("light.den", "control")

    ent_reg.async_update_entity("light.den", labels=set())
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert not kid.permissions.check_entity("light.den", "read")

    client = await hass_ws_client(hass)
    info = await ws_call(client, type="warden/info")
    assert info["labels"] == [{"label_id": kids, "name": "Kids"}]
