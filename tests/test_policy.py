"""Tests for compiling Warden rules into Home Assistant policies.

Each test runs the compiled policy through Home Assistant's own permission
engine, so they check the access a user actually ends up with.
"""

from homeassistant.auth.permissions import PolicyPermissions
from homeassistant.auth.permissions.models import PermissionLookup
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.warden.models import EntityRules
from custom_components.warden.policy import compile_policy


@pytest.fixture
def home(hass: HomeAssistant) -> dict[str, str]:
    """A kitchen device with a light and a lock, plus loose entities."""
    entry = MockConfigEntry(domain="test")
    entry.add_to_hass(hass)
    kitchen = ar.async_get(hass).async_create("Kitchen")
    garage = ar.async_get(hass).async_create("Garage")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("test", "hub")}
    )
    dr.async_get(hass).async_update_device(device.id, area_id=kitchen.id)
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "light", "test", "kitchen", device_id=device.id, suggested_object_id="kitchen"
    )
    ent_reg.async_get_or_create(
        "lock", "test", "back_door", device_id=device.id, suggested_object_id="back"
    )
    garage_light = ent_reg.async_get_or_create(
        "light", "test", "garage", suggested_object_id="garage"
    )
    ent_reg.async_update_entity(garage_light.entity_id, area_id=garage.id)
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("lock.back", "locked")
    hass.states.async_set("light.garage", "off")
    hass.states.async_set("switch.fan", "off")
    return {"kitchen": kitchen.id, "garage": garage.id, "device": device.id}


def perms(hass: HomeAssistant, *rules: EntityRules) -> PolicyPermissions:
    policy, _ = compile_policy(hass, rules)
    return PolicyPermissions(
        policy, PermissionLookup(er.async_get(hass), dr.async_get(hass))
    )


def access(p: PolicyPermissions, entity_id: str) -> str:
    if p.check_entity(entity_id, "control"):
        return "control"
    if p.check_entity(entity_id, "read"):
        return "read"
    return "none"


async def test_no_rules_grants_nothing(hass: HomeAssistant, home: dict) -> None:
    """A group without rules sees nothing."""
    p = perms(hass, EntityRules())
    assert access(p, "light.kitchen") == "none"
    assert not p.access_all_entities("read")


async def test_scopes(hass: HomeAssistant, home: dict) -> None:
    """Domain, area, device and entity rules each grant what they name."""
    assert (
        access(perms(hass, EntityRules(domains={"light": "read"})), "light.garage")
        == "read"
    )
    p = perms(hass, EntityRules(area_ids={home["kitchen"]: "control"}))
    assert access(p, "light.kitchen") == "control"
    assert access(p, "lock.back") == "control"
    assert access(p, "light.garage") == "none"
    p = perms(hass, EntityRules(device_ids={home["device"]: "read"}))
    assert access(p, "lock.back") == "read"
    p = perms(hass, EntityRules(entity_ids={"switch.fan": "control"}))
    assert access(p, "switch.fan") == "control"
    assert access(p, "light.kitchen") == "none"


async def test_highest_level_wins_across_groups(
    hass: HomeAssistant, home: dict
) -> None:
    """Rules from several groups combine; the broadest grant applies."""
    p = perms(
        hass,
        EntityRules(all="read"),
        EntityRules(entity_ids={"light.kitchen": "control"}),
    )
    assert access(p, "light.kitchen") == "control"
    assert access(p, "switch.fan") == "read"


async def test_deny_beats_broader_allow(hass: HomeAssistant, home: dict) -> None:
    """A deny removes an entity even when a broader rule grants it."""
    p = perms(
        hass,
        EntityRules(all="control"),
        EntityRules(domains={"lock": "deny"}),
    )
    assert access(p, "lock.back") == "none"
    assert access(p, "light.kitchen") == "control"
    assert access(p, "switch.fan") == "control"


async def test_deny_beats_more_specific_allow(hass: HomeAssistant, home: dict) -> None:
    """A deny wins even over an allow naming the entity directly."""
    p = perms(
        hass,
        EntityRules(entity_ids={"lock.back": "control"}),
        EntityRules(device_ids={home["device"]: "deny"}),
    )
    assert access(p, "lock.back") == "none"


async def test_area_deny_matches_entity_area(hass: HomeAssistant, home: dict) -> None:
    """An area deny also covers entities placed in the area directly."""
    p = perms(
        hass,
        EntityRules(domains={"light": "control"}, area_ids={home["garage"]: "deny"}),
    )
    assert access(p, "light.garage") == "none"
    assert access(p, "light.kitchen") == "control"


async def test_allow_without_denies_stays_dynamic(
    hass: HomeAssistant, home: dict
) -> None:
    """Without denies, rules stay native and match entities added later."""
    policy, snapshot = compile_policy(hass, [EntityRules(domains={"light": "read"})])
    assert not snapshot
    assert policy == {"entities": {"domains": {"light": {"read": True}}}}
    _, snapshot = compile_policy(
        hass, [EntityRules(domains={"light": "read", "lock": "deny"})]
    )
    # The light rule doesn't touch the denied lock, so it isn't expanded.
    assert not snapshot


async def test_deny_all(hass: HomeAssistant, home: dict) -> None:
    """Denying everything overrides every allow."""
    p = perms(hass, EntityRules(all="control"), EntityRules(all="deny"))
    assert access(p, "light.kitchen") == "none"
