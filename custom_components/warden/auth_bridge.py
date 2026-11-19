"""Manage Home Assistant auth groups for Warden.

Home Assistant's auth store supports custom groups with their own policy (it
loads and saves them), but has no public API to create, change or remove one.
Everything that touches those internals lives here, and is checked on setup so
an incompatible Home Assistant release fails loudly instead of misbehaving.

User membership changes go through the public ``async_update_user``.
"""

from __future__ import annotations

from typing import Any

from homeassistant.auth import models
from homeassistant.core import HomeAssistant

from .const import AUTH_GROUP_PREFIX, LOGGER


class IncompatibleAuthStore(Exception):
    """The auth store doesn't look the way Warden expects."""


def auth_group_id(user_id: str) -> str:
    """Return the id of the auth group holding a user's compiled policy."""
    return f"{AUTH_GROUP_PREFIX}{user_id}"


def is_warden_group(group_id: str) -> bool:
    """Return whether an auth group belongs to Warden."""
    return group_id.startswith(AUTH_GROUP_PREFIX)


class AuthBridge:
    """Create, update and clean up Warden's auth groups."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind to the auth store, verifying the internals Warden relies on."""
        self._hass = hass
        store = getattr(hass.auth, "_store", None)
        groups = getattr(store, "_groups", None)
        if not isinstance(groups, dict) or not callable(
            getattr(store, "_async_schedule_save", None)
        ):
            raise IncompatibleAuthStore(
                "This Home Assistant version's auth store is not supported"
            )
        self._store: Any = store
        self._groups: dict[str, models.Group] = groups

    def group_exists(self, group_id: str) -> bool:
        """Return whether an auth group exists."""
        return group_id in self._groups

    async def async_set_policy(
        self, user: models.User, name: str, policy: dict[str, Any]
    ) -> str:
        """Create or update the user's Warden group; return its id."""
        group_id = auth_group_id(user.id)
        group = self._groups.get(group_id)
        if group is None:
            self._groups[group_id] = models.Group(
                id=group_id, name=name, policy=policy, system_generated=False
            )
            LOGGER.debug("Created auth group %s", group_id)
        elif group.policy != policy or group.name != name:
            group.policy = policy
            group.name = name
            # Users cache their compiled permissions; drop the stale copy.
            for member in await self._hass.auth.async_get_users():
                if any(gr.id == group_id for gr in member.groups):
                    member.invalidate_cache()
            LOGGER.debug("Updated auth group %s", group_id)
        else:
            return group_id
        self._store._async_schedule_save()
        return group_id

    async def async_set_user_groups(
        self, user: models.User, group_ids: list[str]
    ) -> bool:
        """Set the user's groups; return whether anything changed."""
        if [group.id for group in user.groups] == group_ids:
            return False
        await self._hass.auth.async_update_user(user, group_ids=group_ids)
        return True

    async def async_remove_unused(self, keep: set[str] | None = None) -> None:
        """Remove Warden groups no user is in, except those in ``keep``.

        A group must never be removed while a user still references it: the
        auth store would fail to load on the next start.
        """
        keep = keep or set()
        in_use = {
            group.id
            for user in await self._hass.auth.async_get_users()
            for group in user.groups
        }
        stale = [
            group_id
            for group_id in self._groups
            if is_warden_group(group_id) and group_id not in in_use | keep
        ]
        for group_id in stale:
            del self._groups[group_id]
            LOGGER.debug("Removed auth group %s", group_id)
        if stale:
            self._store._async_schedule_save()
