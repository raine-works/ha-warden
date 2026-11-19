"""Constants for the Warden integration."""

import logging

DOMAIN = "warden"
LOGGER = logging.getLogger(__package__)

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

# Every managed user gets exactly one Home Assistant auth group holding their
# compiled policy. Its id is this prefix plus the user id.
AUTH_GROUP_PREFIX = "warden-"

# Access levels for entity rules. "control" implies "read"; "deny" removes
# both and wins over any allow from another rule or group.
LEVEL_READ = "read"
LEVEL_CONTROL = "control"
LEVEL_DENY = "deny"
LEVELS = (LEVEL_READ, LEVEL_CONTROL, LEVEL_DENY)

# Entity rule scopes, most specific first (the order Home Assistant checks).
SCOPE_ENTITY = "entity_ids"
SCOPE_DEVICE = "device_ids"
SCOPE_AREA = "area_ids"
SCOPE_DOMAIN = "domains"
SCOPES = (SCOPE_ENTITY, SCOPE_DEVICE, SCOPE_AREA, SCOPE_DOMAIN)

# Two-factor states reported for a user.
MFA_EXEMPT = "exempt"  # not required
MFA_COMPLIANT = "compliant"  # required and enrolled
MFA_GRACE = "grace"  # required, not enrolled, still inside the grace period
MFA_RESTRICTED = "restricted"  # required, not enrolled, grace period over
MFA_UNENFORCEABLE = "unenforceable"  # required, but no 2FA module is loaded

DEFAULT_GRACE_DAYS = 7

# Sidebar panels.
PANEL_ADMIN = "warden"
PANEL_SECURITY = "warden-security"
PANEL_COMPONENT = "warden-panel"
STATIC_URL = "/warden_static"

# Panels a managed user can always open, whatever their groups allow.
ALWAYS_ALLOWED_PANELS = frozenset({"profile", PANEL_SECURITY})

# The panel key Home Assistant uses for the default dashboard.
DEFAULT_DASHBOARD = "lovelace"

ISSUE_NO_MFA_MODULE = "no_mfa_module"
