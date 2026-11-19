# Warden for Home Assistant

Groups, fine-grained permissions and required two-factor authentication for
[Home Assistant](https://www.home-assistant.io/) users, from
[raine-works](https://github.com/raine-works).

Out of the box, Home Assistant users are either **administrators** or
**users**, and a user can see and control everything. Warden lets you put
people in groups and decide, per group, which entities, devices, areas,
dashboards and sidebar panels they can use, and whether they must use
two-factor authentication.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg?style=for-the-badge)](LICENSE)

[![Test](https://github.com/raine-works/ha-warden/actions/workflows/test.yaml/badge.svg)](https://github.com/raine-works/ha-warden/actions/workflows/test.yaml)
[![Validate](https://github.com/raine-works/ha-warden/actions/workflows/validate.yaml/badge.svg)](https://github.com/raine-works/ha-warden/actions/workflows/validate.yaml)

<a href="https://buymeacoffee.com/raineworks"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee" /></a>

## Features

- **Groups** with any number of members; a person can be in several groups.
- **Entity permissions** by entity, device, area, domain, label, or everything, at
  three levels: **Read**, **Control** (includes read) and **Deny**.
- **Dashboard access**: pick which dashboards a group can open. Others vanish
  from the sidebar, and asking for one directly returns an "access denied"
  page instead of its content.
- **Panel access**: pick which sidebar pages (Map, Energy, Logbook, History,
  To-do lists, add-on panels…) a group can open.
- **Administrator groups**: members become Home Assistant administrators,
  handy for "Parents" or "IT".
- **Required two-factor authentication**, for everyone or per group, with a
  grace period. After the grace period, people who still haven't set it up can
  only reach their profile page until they do; access comes back the moment
  they enroll.
- **A setup prompt** that reaches people who are already logged in, and walks
  them through setting up an authenticator app right there.
- A **Warden** admin panel in the sidebar, and an **Account security** page
  that only appears for people who still need to set up 2FA.

## How it works

Home Assistant already has a permission engine under the hood. It checks every
state read and every entity service call against a per-user *policy*. It just
has no way to configure that policy. Warden compiles each person's groups into
a policy and gives it to Home Assistant, so the enforcement is Home Assistant's
own, everywhere it already checks.

- When someone joins their first group, Warden remembers their current role
  and replaces it with a personal policy built from their groups.
- When they leave their last group, they get their old role back.
- **The owner account is never managed or restricted**, so there is always a
  way back in.

### Administrators

Warden is built so it can't get in the way of administrators:

- **Home Assistant administrators keep full access.** If someone is an
  administrator under **Settings → People**, their groups' entity, dashboard
  and panel rules don't apply to them. Only a group's 2FA requirement does.
  To restrict someone, turn off **Administrator** for them there. Turning it
  back on lifts the restriction.
- **You can't lock yourself out.** Warden refuses a change that would take away
  your own admin access, such as removing yourself from the group that makes
  you an admin. It also refuses to require 2FA with no grace period while you
  haven't set it up yourself. The owner or another admin can still make the
  change.
- **Required 2FA does apply to administrators.** That is deliberate: admin
  accounts matter most. An admin who misses the grace period can only reach
  their profile until they enroll, and then gets admin straight back. The owner
  is always exempt.

### Rules

| Scope | Matches |
| --- | --- |
| Entity | One entity |
| Device | Every entity on a device |
| Area | Every entity on devices in an area |
| Domain | Every entity in a domain (`light`, `lock`, …) |
| Label | Every entity with the label, on a device with it, or in an area with it |
| Every entity | Everything |

Rules from all of a person's groups add up. If any rule grants **Control**, they
can control it; if one grants **Read**, they can see it. **Deny wins over
everything**, from any group and at any scope. That makes "all lights except
the garage", or "everything except the locks", easy to express.

> Area rules follow Home Assistant's own matching: an entity is in the area its
> *device* is in. Area **deny** rules also catch entities assigned to the area
> directly, so a deny never misses anything.

> Labels match the way targeting a label in an action does. Home Assistant's
> permissions have no label scope of their own, so Warden turns a label rule
> into the entities it covers and updates that as you add or remove labels.

### Two-factor authentication

Turn on **Require two-factor authentication** in a group, or for everyone on the
**Two-factor** tab, and set a grace period (0 means immediately).

| State | Meaning |
| --- | --- |
| Grace period | 2FA required, not set up yet. Full access, with a reminder (see below) and an **Account security** page showing the deadline. |
| Restricted | Grace period over. No entities, dashboards or panels except their profile, where they can set up 2FA. Administrators lose admin rights until they enroll. |
| Enrolled | 2FA set up. Normal access. |

**People are prompted wherever they are.** The moment 2FA becomes required for
someone, even if they're already logged in, a dialog opens on whatever page they
have open and walks them through setup: scan a QR code with an authenticator
app, enter the code, done. During the grace period they can choose **Later**
(they're asked again next session). Once restricted, the dialog stays until
they've set it up, or they log out. When they finish, their access comes back
straight away.

The grace clock starts the first time a requirement applies to someone and
keeps running after they enroll, so turning 2FA off later restricts them right
away rather than earning a fresh grace period.

Home Assistant's built-in **Authenticator app** (TOTP) module is loaded by
default. If you've changed `auth_mfa_modules` so that no module is available,
Warden raises a repair and doesn't restrict anyone, since nobody could comply.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=raine-works&repository=ha-warden&category=integration)

1. Click the button above (or in HACS, **⋮ → Custom repositories**, add
   `https://github.com/raine-works/ha-warden` as category **Integration**).
2. Install **Warden**, then restart Home Assistant.

### Manual

Copy `custom_components/warden` into your Home Assistant
`config/custom_components/` directory and restart.

## Setup

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=warden)

1. Click the button above (or go to **Settings → Devices & services → Add
   integration → Warden**) and confirm.
2. Open **Warden** in the sidebar (administrators only) to create groups, add
   members and set two-factor requirements.

Requires Home Assistant 2026.10 or newer.

## What Warden does and doesn't protect

Warden sets the policy; Home Assistant enforces it. Here is where that
enforcement reaches today:

**Enforced for managed users**

- Entity states over the websocket and REST APIs (the frontend, the app,
  long-lived tokens).
- Service calls that target entities (`light.turn_on`, `lock.unlock`, …),
  including calls that target a device or area.
- History.
- Dashboards and sidebar panels (by Warden).

**Not covered**, because Home Assistant doesn't check entity permissions there:

- **Services that don't target entities.** Calling `script.my_script` or
  `notify.mobile_app_x` directly isn't checked. Running a script *as an entity*
  (`script.turn_on` with a target) is. If a script does something sensitive,
  deny its entity and don't expose it as a plain service.
- **Logbook**, and registry listings (device, area and entity names are
  visible, though not their states). Deny the Logbook panel if that matters.
- **Admin-only features** (settings, add-ons, developer tools) were never open
  to non-admins and still aren't.

Deny is the strongest tool you have. For anything sensitive, deny it outright
rather than relying on a narrower allow somewhere else.

## Unloading and removing

- **Disabling, reloading or restarting** keeps everyone's restrictions in place.
  Warden never widens access by being switched off. (Dashboard and panel
  filtering pauses while it's disabled; entity permissions stay.)
- **Deleting the integration** (Settings → Devices & services → Warden →
  Delete) gives every managed user their original role back and removes
  Warden's data. Do this **before** deleting the files, or managed users keep
  their Warden policy.

## Compatibility

Home Assistant stores custom
permission groups in its auth data, but has no public API for creating them, so
Warden writes them through a small internal bridge (`auth_bridge.py`). It checks
those internals on startup and refuses to load, with an error, if they ever
change, rather than guess.

## Development

```bash
uv venv -p 3.14 .venv
uv pip install -p .venv -r requirements-test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest -q
```

The tests run Warden inside a real Home Assistant and check access through Home
Assistant's own permission engine.

## Contributing

Issues and PRs welcome. This is a community project maintained on a best-effort
basis. If something breaks, please include your Home Assistant version, what the
affected user's groups allow, and any relevant Home Assistant logs.

## ☕ Support

If you find this project helpful, consider buying me a coffee to support continued
maintenance and development:

<a href="https://buymeacoffee.com/raineworks"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee" /></a>

## License

[MIT](LICENSE) © [Raine Petersen](https://github.com/raine-works)
