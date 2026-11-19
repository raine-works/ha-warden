"""Data model for Warden groups, settings and per-user state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .const import DEFAULT_GRACE_DAYS, SCOPES


@dataclass
class EntityRules:
    """Entity access rules: a level for everything, plus levels by scope."""

    all: str | None = None
    entity_ids: dict[str, str] = field(default_factory=dict)
    device_ids: dict[str, str] = field(default_factory=dict)
    area_ids: dict[str, str] = field(default_factory=dict)
    domains: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityRules:
        """Build from stored data."""
        return cls(
            all=data.get("all"),
            **{scope: dict(data.get(scope, {})) for scope in SCOPES},
        )

    def scope(self, scope: str) -> dict[str, str]:
        """Return the rules for one scope."""
        return getattr(self, scope)


@dataclass
class AccessList:
    """Access to a set of named UI resources (dashboards or panels)."""

    all: bool = False
    items: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccessList:
        """Build from stored data."""
        return cls(all=bool(data.get("all", False)), items=list(data.get("items", [])))


@dataclass
class WardenGroup:
    """A group of users sharing permissions and a 2FA requirement."""

    id: str
    name: str
    description: str = ""
    # Members become Home Assistant administrators. Entity, dashboard and panel
    # rules don't apply to them, but the 2FA requirement still does.
    admin: bool = False
    require_mfa: bool = False
    members: list[str] = field(default_factory=list)
    entities: EntityRules = field(default_factory=EntityRules)
    dashboards: AccessList = field(default_factory=AccessList)
    panels: AccessList = field(default_factory=AccessList)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WardenGroup:
        """Build from stored data."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            admin=bool(data.get("admin", False)),
            require_mfa=bool(data.get("require_mfa", False)),
            members=list(data.get("members", [])),
            entities=EntityRules.from_dict(data.get("entities", {})),
            dashboards=AccessList.from_dict(data.get("dashboards", {})),
            panels=AccessList.from_dict(data.get("panels", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage and the websocket API."""
        return asdict(self)


@dataclass
class Settings:
    """Global Warden settings."""

    # Require 2FA for every user (except the owner), grouped or not.
    require_mfa_all: bool = False
    # Days a user may keep using Home Assistant before enrolling in 2FA.
    mfa_grace_days: int = DEFAULT_GRACE_DAYS

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        """Build from stored data."""
        return cls(
            require_mfa_all=bool(data.get("require_mfa_all", False)),
            mfa_grace_days=int(data.get("mfa_grace_days", DEFAULT_GRACE_DAYS)),
        )


@dataclass
class UserRecord:
    """What Warden remembers about a user it has touched."""

    # The user's Home Assistant groups before Warden took them over, restored
    # when Warden lets go of the user. None until Warden takes over.
    original_group_ids: list[str] | None = None
    # When the user first became subject to a 2FA requirement (ISO 8601).
    mfa_required_since: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserRecord:
        """Build from stored data."""
        return cls(
            original_group_ids=data.get("original_group_ids"),
            mfa_required_since=data.get("mfa_required_since"),
        )

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing worth keeping."""
        return self.original_group_ids is None and self.mfa_required_since is None


@dataclass
class UiAccess:
    """The dashboards and panels a restricted user may open."""

    dashboards: AccessList
    panels: AccessList

    def allows_dashboard(self, url_path: str) -> bool:
        """Return whether the dashboard may be opened."""
        return self.dashboards.all or url_path in self.dashboards.items

    def allows_panel(self, url_path: str) -> bool:
        """Return whether the panel may be opened."""
        return self.panels.all or url_path in self.panels.items
