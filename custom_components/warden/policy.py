"""Compile Warden entity rules into a Home Assistant auth policy.

Home Assistant's permission engine checks a policy's entity scopes from most to
least specific (entity, device, area, domain, all) and takes the first scope
with an opinion. Its leaves can only grant, so the effect is a union: a user
may do something if any rule matching the entity allows it.

Warden adds "deny", which wins over every allow. Home Assistant can't express a
deny (its policy merger rejects anything but ``True`` leaves), so a deny is
applied at compile time: each allow rule that covers a denied entity is
replaced by explicit grants for the entities it covers, minus the denied ones.
Allow rules that touch no denied entity stay as native scope rules, so they
keep matching devices and entities added later without a recompile.

Labels work the same way: Home Assistant's policies have no label scope, so
a label rule is always expanded into the entities it covers.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.auth.permissions import POLICY_SCHEMA
from homeassistant.auth.permissions.const import (
    CAT_ENTITIES,
    POLICY_CONTROL,
    POLICY_READ,
    SUBCAT_ALL,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from .const import (
    LEVEL_CONTROL,
    LEVEL_DENY,
    LEVEL_READ,
    POLICY_SCOPES,
    SCOPE_AREA,
    SCOPE_DEVICE,
    SCOPE_DOMAIN,
    SCOPE_ENTITY,
    SCOPE_LABEL,
    SCOPES,
)
from .models import EntityRules

_RANK = {None: 0, LEVEL_READ: 1, LEVEL_CONTROL: 2}

# A policy that grants nothing. An empty entities dict denies everything.
DENY_ALL_POLICY: dict[str, Any] = {CAT_ENTITIES: {}}


def _max_level(a: str | None, b: str | None) -> str | None:
    return a if _RANK[a] >= _RANK[b] else b


def _grant(level: str) -> dict[str, bool]:
    if level == LEVEL_CONTROL:
        return {POLICY_READ: True, POLICY_CONTROL: True}
    return {POLICY_READ: True}


class EntityIndex:
    """Facts about entities that rules match on, read from the registries."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Snapshot the registries."""
        self._hass = hass
        self._ent_reg = er.async_get(hass)
        self._dev_reg = dr.async_get(hass)
        self._area_reg = ar.async_get(hass)

    @callback
    def entity_ids(self) -> set[str]:
        """Return every known entity id, registered or not."""
        return set(self._hass.states.async_entity_ids()) | set(
            self._ent_reg.entities.keys()
        )

    @callback
    def device_id(self, entity_id: str) -> str | None:
        """Return the entity's device."""
        entry = self._ent_reg.async_get(entity_id)
        return entry.device_id if entry else None

    @callback
    def device_area_id(self, entity_id: str) -> str | None:
        """Return the area of the entity's device.

        This is the area Home Assistant's permission engine matches area rules
        against; it ignores an area set on the entity itself.
        """
        if (device_id := self.device_id(entity_id)) is None:
            return None
        if (device := self._dev_reg.async_get(device_id)) is None:
            return None
        return dr.async_get_effective_area_id(self._hass, device)

    @callback
    def entity_area_id(self, entity_id: str) -> str | None:
        """Return the area set on the entity itself, if any."""
        entry = self._ent_reg.async_get(entity_id)
        return entry.area_id if entry else None

    @callback
    def label_ids(self, entity_id: str) -> set[str]:
        """Return the labels that make a label rule match the entity.

        Like targeting a label in an action: labels on the entity, on its
        device, and on its area (its own, or else its device's).
        """
        if (entry := self._ent_reg.async_get(entity_id)) is None:
            return set()
        labels = set(entry.labels)
        area_id = entry.area_id
        if entry.device_id and (device := self._dev_reg.async_get(entry.device_id)):
            labels |= device.labels
            area_id = area_id or device.area_id
        if area_id and (area := self._area_reg.async_get_area(area_id)):
            labels |= area.labels
        return labels


def _covers(index: EntityIndex, entity_id: str, scope: str, key: str) -> bool:
    """Return whether an allow rule matches, the way Home Assistant matches it."""
    if scope == SCOPE_ENTITY:
        return entity_id == key
    if scope == SCOPE_DEVICE:
        return index.device_id(entity_id) == key
    if scope == SCOPE_AREA:
        return index.device_area_id(entity_id) == key
    if scope == SCOPE_LABEL:
        return key in index.label_ids(entity_id)
    return entity_id.partition(".")[0] == key


def _denied(index: EntityIndex, entity_id: str, scope: str, key: str) -> bool:
    """Return whether a deny rule matches.

    Area denies also match entities placed in the area directly, so a deny
    never misses something a person would consider to be in that area.
    """
    if scope == SCOPE_AREA and index.entity_area_id(entity_id) == key:
        return True
    return _covers(index, entity_id, scope, key)


class MergedRules:
    """The union of several groups' rules, with denies kept apart."""

    def __init__(self, rules: Iterable[EntityRules]) -> None:
        """Merge rules: highest allow wins per key, any deny wins outright."""
        self.all: str | None = None
        self.deny_all = False
        self.allow: dict[str, dict[str, str]] = {scope: {} for scope in SCOPES}
        self.deny: dict[str, set[str]] = {scope: set() for scope in SCOPES}
        for rule in rules:
            if rule.all == LEVEL_DENY:
                self.deny_all = True
            elif rule.all is not None:
                self.all = _max_level(self.all, rule.all)
            for scope in SCOPES:
                for key, level in rule.scope(scope).items():
                    if level == LEVEL_DENY:
                        self.deny[scope].add(key)
                    else:
                        self.allow[scope][key] = _max_level(
                            self.allow[scope].get(key), level
                        )

    @property
    def has_denies(self) -> bool:
        """Return whether any scoped deny exists."""
        return any(self.deny.values())


@callback
def compile_policy(
    hass: HomeAssistant, rules: Iterable[EntityRules]
) -> tuple[dict[str, Any], bool]:
    """Compile rules into a policy.

    Returns the policy and whether it depends on a snapshot of the registries
    (true when denies forced allow rules to be expanded), in which case it must
    be recompiled when entities, devices or areas change.
    """
    merged = MergedRules(rules)
    if merged.deny_all:
        return DENY_ALL_POLICY, False

    allow = {scope: dict(keys) for scope, keys in merged.allow.items()}
    allow_all = merged.all
    expanded = False
    labels = allow.pop(SCOPE_LABEL)

    if merged.has_denies or labels:
        index = EntityIndex(hass)
        universe = index.entity_ids()
        denied = {
            entity_id
            for entity_id in universe
            if any(
                _denied(index, entity_id, scope, key)
                for scope, keys in merged.deny.items()
                for key in keys
            )
        }
        # A denied key named directly is denied even if no entity exists yet.
        denied |= merged.deny[SCOPE_ENTITY]

        grants: dict[str, str] = {}

        def expand(covered: Iterable[str], level: str) -> None:
            for entity_id in covered:
                if entity_id not in denied:
                    grants[entity_id] = _max_level(grants.get(entity_id), level)

        if allow_all is not None and merged.has_denies:
            expand(universe, allow_all)
            allow_all = None
            expanded = True

        for scope in (SCOPE_DEVICE, SCOPE_AREA, SCOPE_DOMAIN):
            for key, level in list(allow[scope].items()):
                covered = {e for e in universe if _covers(index, e, scope, key)}
                if covered & denied:
                    del allow[scope][key]
                    expand(covered, level)
                    expanded = True

        for key, level in labels.items():
            expand((e for e in universe if _covers(index, e, SCOPE_LABEL, key)), level)
            expanded = True

        for entity_id in denied:
            allow[SCOPE_ENTITY].pop(entity_id, None)
        for entity_id, level in grants.items():
            allow[SCOPE_ENTITY][entity_id] = _max_level(
                allow[SCOPE_ENTITY].get(entity_id), level
            )

    entities: dict[str, Any] = {}
    # Never emit a bare boolean for a scope: Home Assistant reads any boolean
    # there, even False, as "allow everything".
    if allow_all is not None:
        entities[SUBCAT_ALL] = _grant(allow_all)
    for scope in POLICY_SCOPES:
        if allow[scope]:
            entities[scope] = {
                key: _grant(level) for key, level in sorted(allow[scope].items())
            }

    policy = {CAT_ENTITIES: entities}
    POLICY_SCHEMA(policy)
    return policy, expanded
