"""The public API other integrations read groups through."""

from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.warden import api
from custom_components.warden.manager import WardenManager


async def test_nothing_while_warden_is_not_loaded(hass: HomeAssistant) -> None:
    assert api.async_get_groups(hass) is None
    assert api.async_get_group(hass, "anything") is None


async def test_groups_and_their_members(
    hass: HomeAssistant, warden: WardenManager, make_user: Any
) -> None:
    kid = await make_user("Kid")
    teen = await make_user("Teen")
    family = await warden.async_create_group({"name": "family", "members": [kid.id]})
    await warden.async_create_group(
        {
            "name": "Adults",
            "description": "Parents",
            "admin": True,
            "members": [teen.id],
        }
    )

    groups = api.async_get_groups(hass)
    assert [group.name for group in groups] == ["Adults", "family"]
    assert groups[0].admin is True
    assert groups[0].description == "Parents"
    assert groups[1].members == frozenset({kid.id})

    assert api.async_get_group(hass, family.id) == groups[1]
    assert api.async_get_group(hass, "gone") is None


async def test_returns_copies(
    hass: HomeAssistant, warden: WardenManager, make_user: Any
) -> None:
    kid = await make_user("Kid")
    group = await warden.async_create_group({"name": "Family", "members": [kid.id]})
    seen = api.async_get_group(hass, group.id)
    assert isinstance(seen.members, frozenset)
    # The group itself still has its own list
    assert warden.store.groups[group.id].members == [kid.id]
