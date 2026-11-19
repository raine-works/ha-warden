"""Persistent Warden configuration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import Settings, UserRecord, WardenGroup


class WardenStore:
    """Groups, settings and per-user records, saved to .storage/warden."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY, private=True, atomic_writes=True
        )
        self.groups: dict[str, WardenGroup] = {}
        self.settings = Settings()
        self.users: dict[str, UserRecord] = {}

    async def async_load(self) -> None:
        """Load from disk."""
        if (data := await self._store.async_load()) is None:
            return
        self.groups = {
            group["id"]: WardenGroup.from_dict(group) for group in data["groups"]
        }
        self.settings = Settings.from_dict(data.get("settings", {}))
        self.users = {
            user_id: UserRecord.from_dict(record)
            for user_id, record in data.get("users", {}).items()
        }

    @callback
    def async_schedule_save(self) -> None:
        """Save soon."""
        self._store.async_delay_save(self._data_to_save, 1)

    async def async_save(self) -> None:
        """Save now."""
        await self._store.async_save(self._data_to_save())

    async def async_remove(self) -> None:
        """Delete the stored data."""
        await self._store.async_remove()

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        return {
            "groups": [group.to_dict() for group in self.groups.values()],
            "settings": {
                "require_mfa_all": self.settings.require_mfa_all,
                "mfa_grace_days": self.settings.mfa_grace_days,
            },
            "users": {
                user_id: {
                    "original_group_ids": record.original_group_ids,
                    "mfa_required_since": record.mfa_required_since,
                    "applied_group_ids": record.applied_group_ids,
                }
                for user_id, record in self.users.items()
                if not record.is_empty
            },
        }

    @callback
    def groups_for_user(self, user_id: str) -> list[WardenGroup]:
        """Return the groups a user belongs to."""
        return [group for group in self.groups.values() if user_id in group.members]

    @callback
    def record(self, user_id: str) -> UserRecord:
        """Return the user's record, creating an empty one if needed."""
        return self.users.setdefault(user_id, UserRecord())
