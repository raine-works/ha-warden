# Groups and permissions

A group has members and rules. A person can be in several groups.

## Group fields

| Field | Meaning |
| :--- | :--- |
| Name | Required |
| Description | Optional text |
| Administrator | Members become Home Assistant administrators |
| Require two-factor authentication | Members must set up 2FA. See [Two-factor authentication](two-factor.md) |
| Members | Home Assistant users. The owner and system users can't be members |
| Entities | Entity rules, below |
| Dashboards | All dashboards, or a chosen list |
| Panels | All sidebar panels, or a chosen list |

## Entity rules

A rule gives a scope a level.

| Scope | Matches |
| :--- | :--- |
| Entity | One entity |
| Device | Every entity on a device |
| Area | Every entity on devices in an area |
| Domain | Every entity in a domain (`light`, `lock`, …) |
| Label | Every entity with the label, on a device with it, or in an area with it |
| Every entity | Everything |

| Level | Meaning |
| :--- | :--- |
| Read | The person can see the state |
| Control | The person can control it. Includes read |
| Deny | Removes both. Wins over any allow |

Rules from all of a person's groups add up. If any rule grants Control, they can control the entity. If one grants Read, they can see it. Deny wins over everything, from any group and at any scope. That makes "all lights except the garage" or "everything except the locks" easy to express.

Area rules follow Home Assistant's matching: an entity is in the area its device is in. Area deny rules also catch entities assigned to the area directly, so a deny never misses anything.

Home Assistant's permissions have no label scope. Warden turns a label rule into the entities it covers, and updates that as you add or remove labels. Labels match the way targeting a label in an action does.

## Dashboards

Pick which dashboards a group can open. Others vanish from the sidebar. Asking for one directly returns an "access denied" page instead of its content. If someone may not open the default dashboard, they get their first allowed dashboard instead.

## Panels

Pick which sidebar pages (Map, Energy, Logbook, History, To-do lists, add-on panels and so on) a group can open. Administrator-only panels never appear in the list. These panels are always allowed, whatever the groups say: the profile page, **Account security**, and Home Assistant's "not found" page. The last one stays so a person whose groups allow no panels doesn't get a frontend stuck on its loading screen.

## Administrators

- **Home Assistant administrators keep full access.** If someone is an administrator under **Settings → People**, their groups' entity, dashboard and panel rules don't apply to them. Only a group's 2FA requirement does. To restrict someone, turn off **Administrator** for them there.
- **Administrator groups.** Members of a group marked Administrator become Home Assistant administrators. Entity, dashboard and panel rules don't apply to them.
- **You can't lock yourself out.** Warden refuses a change that would take away your own admin access, such as removing yourself from the group that makes you an admin. It also refuses to require 2FA with no grace period while you haven't set it up yourself. The owner or another administrator can make the change.
- **Required 2FA does apply to administrators.** See [Two-factor authentication](two-factor.md).

If someone's groups are changed outside Warden, for example with the Administrator toggle under **Settings → People**, Warden treats that as their new role. It decides whether they're an administrator, and it's what they get back when Warden lets go of them.
