"""Warden's public API, for other integrations: read-only views of the groups.

Import it guarded, since Warden may not be installed:

    try:
        from custom_components.warden import api as warden
    except ImportError:
        warden = None

    groups = warden.async_get_groups(hass) if warden else None

Everything here is read-only and returns copies, so a caller can't change
Warden's groups or anyone's access through it. The shapes stay stable across
Warden releases; Warden's other modules are internal and may change.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


@dataclass(frozen=True, slots=True)
class GroupInfo:
    """A Warden group as other integrations see it."""

    id: str
    name: str
    description: str
    # Home Assistant user ids
    members: frozenset[str]
    # Members become Home Assistant administrators
    admin: bool


def _groups(hass: HomeAssistant) -> dict | None:
    manager = hass.data.get(DOMAIN)
    return manager.store.groups if manager is not None else None


@callback
def async_get_groups(hass: HomeAssistant) -> list[GroupInfo] | None:
    """Every group, sorted by name; None while Warden isn't loaded."""
    groups = _groups(hass)
    if groups is None:
        return None
    return sorted(
        (
            GroupInfo(
                id=group.id,
                name=group.name,
                description=group.description,
                members=frozenset(group.members),
                admin=group.admin,
            )
            for group in groups.values()
        ),
        key=lambda group: (group.name.casefold(), group.id),
    )


@callback
def async_get_group(hass: HomeAssistant, group_id: str) -> GroupInfo | None:
    """One group by id; None while Warden isn't loaded, or there's no such group."""
    return next(
        (group for group in async_get_groups(hass) or [] if group.id == group_id),
        None,
    )
