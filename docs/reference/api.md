# Python and websocket API

## Python API for other integrations

Other integrations can read Warden's groups, read-only, through `custom_components.warden.api`. For example, an integration can treat a group's members as a household. Import it guarded, since Warden may not be installed.

```python
try:
    from custom_components.warden import api as warden
except ImportError:
    warden = None

groups = warden.async_get_groups(hass) if warden else None  # None: Warden isn't loaded
family = warden.async_get_group(hass, group_id) if warden else None
if family:
    user_ids = family.members  # frozenset of Home Assistant user ids
```

| Function | Returns |
| :--- | :--- |
| `async_get_groups(hass)` | Every group sorted by name, or `None` while Warden isn't loaded |
| `async_get_group(hass, group_id)` | One group, or `None` if Warden isn't loaded or there is no such group |

A `GroupInfo` is frozen and has these fields.

| Field | Type |
| :--- | :--- |
| `id` | `str` |
| `name` | `str` |
| `description` | `str` |
| `members` | `frozenset[str]` of user ids |
| `admin` | `bool`, members become administrators |

These shapes stay stable across releases. Warden's other modules are internal.

## Websocket commands

These back the Warden panels. They are not a stable API.

| Command | Who | Fields |
| :--- | :--- | :--- |
| `warden/info` | Administrators | None. Returns groups, settings, users, dashboards, panels, labels and 2FA modules |
| `warden/group/create` | Administrators | `name`, plus the optional group fields |
| `warden/group/update` | Administrators | `group_id`, optional `name`, plus the optional group fields |
| `warden/group/delete` | Administrators | `group_id` |
| `warden/settings/update` | Administrators | `require_mfa_all`, `mfa_grace_days` (0 to 365) |
| `warden/me` | Any user | None. Returns the user's own status |
| `warden/me/subscribe` | Any user | None. Sends the status now and when it changes |

The optional group fields are `description`, `admin`, `require_mfa`, `members`, `entities`, `dashboards` and `panels`. `entities` holds `all` and a map of id to level per scope: `entity_ids`, `device_ids`, `area_ids`, `domains`, `label_ids`. Levels are `read`, `control` and `deny`. `dashboards` and `panels` hold `all` and `items`.
