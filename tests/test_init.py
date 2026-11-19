"""End-to-end tests: users, groups, guards and required 2FA."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.auth.auth_store import AuthStore
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.warden.const import DOMAIN, PANEL_SECURITY
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


async def test_external_group_change_is_reverted_and_remembered(
    hass: HomeAssistant, warden: WardenManager, hass_ws_client: Any, make_user: Any
) -> None:
    """Changing a managed user's groups elsewhere doesn't escape Warden."""
    kid = await make_user()
    group = await create_group(hass, hass_ws_client, name="Kids", members=[kid.id])

    await hass.auth.async_update_user(kid, group_ids=[GROUP_ID_ADMIN])
    await hass.async_block_till_done()
    assert group_ids(kid) == [f"warden-{kid.id}"]

    # ...but it is what they get back when Warden releases them.
    client = await hass_ws_client(hass)
    await ws_call(client, type="warden/group/update", group_id=group["id"], members=[])
    await hass.async_block_till_done()
    assert group_ids(kid) == [GROUP_ID_ADMIN]


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
    make_user: Any,
) -> None:
    """The global setting covers ungrouped users, and spares the owner."""
    hass.states.async_set("light.den", "on")
    user = await make_user("Guest")
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
