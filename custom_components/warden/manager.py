"""Keep Home Assistant users in line with Warden's groups and 2FA rules."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from typing import Any
import uuid

from homeassistant.auth import EVENT_USER_ADDED, EVENT_USER_REMOVED, EVENT_USER_UPDATED
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.auth.models import User
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .auth_bridge import AuthBridge, is_warden_group
from .const import (
    DOMAIN,
    ISSUE_NO_MFA_MODULE,
    LOGGER,
    MFA_COMPLIANT,
    MFA_EXEMPT,
    MFA_GRACE,
    MFA_RESTRICTED,
    MFA_UNENFORCEABLE,
)
from .models import AccessList, Settings, UiAccess, WardenGroup
from .policy import DENY_ALL_POLICY, compile_policy
from .store import WardenStore

SIGNAL_UPDATED = f"{DOMAIN}_updated"

# Grace periods expire on their own; check this often.
RECHECK_INTERVAL = timedelta(minutes=5)


@dataclass
class UserStatus:
    """Warden's view of one user, as of the last reconcile."""

    managed: bool
    admin: bool
    mfa: str
    mfa_deadline: datetime | None
    # None means Warden doesn't limit which dashboards and panels they open.
    ui: UiAccess | None


def manageable(user: User) -> bool:
    """Return whether Warden may manage a user.

    The owner always has full access in Home Assistant whatever their groups,
    and is left alone so there is always a way back in.
    """
    return not user.system_generated and not user.is_owner


class WardenManager:
    """Reconciles users with Warden's configuration."""

    def __init__(self, hass: HomeAssistant, store: WardenStore) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.store = store
        self.bridge = AuthBridge(hass)
        self.status: dict[str, UserStatus] = {}
        self._lock = asyncio.Lock()
        self._unsubs: list[Callable[[], None]] = []
        # Users whose policy was compiled against a registry snapshot.
        self._snapshot_users: set[str] = set()
        self._registry_debouncer = Debouncer(
            hass,
            LOGGER,
            cooldown=2,
            immediate=False,
            function=self.async_reconcile_all,
        )
        self._original_mfa_calls: list[tuple[Any, str, Any]] = []

    async def async_start(self) -> None:
        """Reconcile everyone and start listening for changes."""
        await self._async_prune_missing_users()
        await self.async_reconcile_all()

        hass = self.hass
        for event_type in (EVENT_USER_ADDED, EVENT_USER_UPDATED):
            self._unsubs.append(hass.bus.async_listen(event_type, self._on_user_event))
        self._unsubs.append(
            hass.bus.async_listen(EVENT_USER_REMOVED, self._on_user_removed)
        )
        for event_type in (
            er.EVENT_ENTITY_REGISTRY_UPDATED,
            dr.EVENT_DEVICE_REGISTRY_UPDATED,
            ar.EVENT_AREA_REGISTRY_UPDATED,
        ):
            self._unsubs.append(hass.bus.async_listen(event_type, self._on_registry))
        self._unsubs.append(
            hass.bus.async_listen(
                EVENT_STATE_CHANGED,
                self._on_registry,
                event_filter=_is_new_entity,
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                hass, self._on_interval, RECHECK_INTERVAL, name="warden recheck"
            )
        )
        self._hook_mfa_changes()

    @callback
    def async_stop(self) -> None:
        """Stop listening. Users keep their current groups and policies."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._registry_debouncer.async_shutdown()
        for module, name, original in self._original_mfa_calls:
            setattr(module, name, original)
        self._original_mfa_calls.clear()

    # ----------------------------------------------------------------- events

    @callback
    def _on_user_event(self, event: Event) -> None:
        self.hass.async_create_task(self.async_reconcile_user_id(event.data["user_id"]))

    @callback
    def _on_user_removed(self, event: Event) -> None:
        self.hass.async_create_task(self._async_forget_user(event.data["user_id"]))

    @callback
    def _on_registry(self, event: Event) -> None:
        if self._snapshot_users:
            self._registry_debouncer.async_schedule_call()

    async def _on_interval(self, _now: datetime) -> None:
        await self.async_reconcile_all()

    def _hook_mfa_changes(self) -> None:
        """Reconcile a user right after they enable or disable a 2FA method.

        Home Assistant fires no event for this. Its setup flow (behind the
        profile page) calls the module's ``async_setup_user`` directly, and the
        auth manager's enable/disable calls also end up in the module, so the
        module methods are the one place that sees every change.
        """
        for module in self.hass.auth.auth_mfa_modules:
            for name in ("async_setup_user", "async_depose_user"):
                original = getattr(module, name)
                self._original_mfa_calls.append((module, name, original))
                setattr(module, name, self._wrap_mfa_call(original))

    def _wrap_mfa_call(self, call: Any) -> Any:
        @wraps(call)
        async def wrapper(user_id: str, *args: Any, **kwargs: Any) -> Any:
            result = await call(user_id, *args, **kwargs)
            await self.async_reconcile_user_id(user_id)
            return result

        return wrapper

    # -------------------------------------------------------------- reconcile

    async def async_reconcile_all(self) -> None:
        """Bring every user in line with the configuration."""
        async with self._lock:
            self._update_mfa_issue()
            for user in await self.hass.auth.async_get_users():
                await self._async_reconcile(user)
            await self.bridge.async_remove_unused()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    async def async_reconcile_user_id(self, user_id: str) -> None:
        """Bring one user in line with the configuration."""
        if (user := await self.hass.auth.async_get_user(user_id)) is None:
            return
        async with self._lock:
            await self._async_reconcile(user)
            await self.bridge.async_remove_unused()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    async def _async_reconcile(self, user: User) -> None:
        if not manageable(user):
            self.status.pop(user.id, None)
            return

        groups = self.store.groups_for_user(user.id)
        mfa, deadline = await self._async_mfa_state(user, groups)
        managed = bool(groups)
        restricted = mfa == MFA_RESTRICTED
        wants_admin = any(group.admin for group in groups)
        admin = wants_admin and not restricted

        if not managed and not restricted:
            await self._async_release(user)
            self.status[user.id] = UserStatus(False, user.is_admin, mfa, deadline, None)
            return

        record = self.store.record(user.id)
        current = [group.id for group in user.groups]
        if record.original_group_ids is None:
            record.original_group_ids = current
            self.store.async_schedule_save()
        elif not any(is_warden_group(g) for g in current) and not (
            wants_admin and current == [GROUP_ID_ADMIN]
        ):
            # Someone changed this user's groups outside Warden (for example
            # with the administrator toggle). Restore that when releasing them.
            record.original_group_ids = current
            self.store.async_schedule_save()

        snapshot = False
        if admin:
            desired = [GROUP_ID_ADMIN]
        else:
            if restricted:
                policy = DENY_ALL_POLICY
            else:
                policy, snapshot = compile_policy(
                    self.hass, [group.entities for group in groups]
                )
            desired = [
                await self.bridge.async_set_policy(
                    user, f"Warden: {user.name or user.id}", policy
                )
            ]
        if snapshot:
            self._snapshot_users.add(user.id)
        else:
            self._snapshot_users.discard(user.id)

        await self.bridge.async_set_user_groups(user, desired)

        if restricted:
            ui: UiAccess | None = UiAccess(AccessList(), AccessList())
        elif admin:
            ui = None
        else:
            ui = UiAccess(
                _union(group.dashboards for group in groups),
                _union(group.panels for group in groups),
            )
        self.status[user.id] = UserStatus(managed, admin, mfa, deadline, ui)

    async def _async_release(self, user: User) -> None:
        """Give a user back the groups they had before Warden took over."""
        self._snapshot_users.discard(user.id)
        record = self.store.users.get(user.id)
        if record is None or record.original_group_ids is None:
            return
        restore = [
            group_id
            for group_id in record.original_group_ids
            if self.bridge.group_exists(group_id) and not is_warden_group(group_id)
        ] or [GROUP_ID_USER]
        await self.bridge.async_set_user_groups(user, restore)
        record.original_group_ids = None
        self.store.async_schedule_save()
        LOGGER.info("Released %s from Warden", user.name)

    async def _async_mfa_state(
        self, user: User, groups: list[WardenGroup]
    ) -> tuple[str, datetime | None]:
        """Return the user's 2FA state and when their grace period ends."""
        settings = self.store.settings
        required = settings.require_mfa_all or any(g.require_mfa for g in groups)
        record = self.store.record(user.id)
        if not required:
            if record.mfa_required_since is not None:
                record.mfa_required_since = None
                self.store.async_schedule_save()
            return MFA_EXEMPT, None

        # The clock starts the first time the requirement applies and keeps
        # running after enrollment, so disabling 2FA later gets no new grace.
        if record.mfa_required_since is None:
            record.mfa_required_since = dt_util.utcnow().isoformat()
            self.store.async_schedule_save()
        since = dt_util.parse_datetime(record.mfa_required_since) or dt_util.utcnow()
        deadline = since + timedelta(days=settings.mfa_grace_days)

        if await self.hass.auth.async_get_enabled_mfa(user):
            return MFA_COMPLIANT, None
        if not self.hass.auth.auth_mfa_modules:
            return MFA_UNENFORCEABLE, None
        if dt_util.utcnow() < deadline:
            return MFA_GRACE, deadline
        return MFA_RESTRICTED, deadline

    @callback
    def _update_mfa_issue(self) -> None:
        """Raise a repair if 2FA is required but can't be set up."""
        required = self.store.settings.require_mfa_all or any(
            group.require_mfa for group in self.store.groups.values()
        )
        if required and not self.hass.auth.auth_mfa_modules:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_NO_MFA_MODULE,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_NO_MFA_MODULE,
                learn_more_url="https://www.home-assistant.io/docs/authentication/multi-factor-auth/",
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_NO_MFA_MODULE)

    async def _async_prune_missing_users(self) -> None:
        """Drop users that no longer exist from groups and records."""
        existing = {user.id for user in await self.hass.auth.async_get_users()}
        for group in self.store.groups.values():
            group.members = [m for m in group.members if m in existing]
        for user_id in list(self.store.users):
            if user_id not in existing:
                del self.store.users[user_id]
        self.store.async_schedule_save()

    async def _async_forget_user(self, user_id: str) -> None:
        async with self._lock:
            for group in self.store.groups.values():
                if user_id in group.members:
                    group.members.remove(user_id)
            self.store.users.pop(user_id, None)
            self.status.pop(user_id, None)
            self._snapshot_users.discard(user_id)
            self.store.async_schedule_save()
            await self.bridge.async_remove_unused()
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    async def async_release_all(self) -> None:
        """Hand every user back their original groups (on removal)."""
        async with self._lock:
            for user in await self.hass.auth.async_get_users():
                await self._async_release(user)
            await self.bridge.async_remove_unused()
        await self.store.async_save()

    # ---------------------------------------------------------------- changes

    async def async_create_group(self, data: dict[str, Any]) -> WardenGroup:
        """Create a group."""
        group = WardenGroup.from_dict({**data, "id": uuid.uuid4().hex})
        self.store.groups[group.id] = group
        await self._async_changed()
        return group

    async def async_update_group(
        self, group_id: str, data: dict[str, Any]
    ) -> WardenGroup:
        """Replace a group's fields with those given."""
        group = WardenGroup.from_dict(
            {**self.store.groups[group_id].to_dict(), **data, "id": group_id}
        )
        self.store.groups[group_id] = group
        await self._async_changed()
        return group

    async def async_delete_group(self, group_id: str) -> None:
        """Delete a group."""
        del self.store.groups[group_id]
        await self._async_changed()

    async def async_update_settings(self, data: dict[str, Any]) -> Settings:
        """Change global settings."""
        settings = self.store.settings
        self.store.settings = Settings(
            require_mfa_all=data.get("require_mfa_all", settings.require_mfa_all),
            mfa_grace_days=data.get("mfa_grace_days", settings.mfa_grace_days),
        )
        await self._async_changed()
        return self.store.settings

    async def _async_changed(self) -> None:
        self.store.async_schedule_save()
        await self.async_reconcile_all()

    # ----------------------------------------------------------------- lookup

    @callback
    def ui_access(self, user: User) -> UiAccess | None:
        """Return the dashboards and panels a user may open (None: any)."""
        if (status := self.status.get(user.id)) is None:
            return None
        return status.ui

    @callback
    def needs_mfa_attention(self, user: User) -> bool:
        """Return whether the user must still set up 2FA."""
        status = self.status.get(user.id)
        return status is not None and status.mfa in (MFA_GRACE, MFA_RESTRICTED)


@callback
def _is_new_entity(data: Any) -> bool:
    """Match state changes that mean an entity just appeared."""
    return data["old_state"] is None


def _union(lists: Any) -> AccessList:
    merged = AccessList()
    for access in lists:
        merged.all = merged.all or access.all
        merged.items.extend(i for i in access.items if i not in merged.items)
    return merged
