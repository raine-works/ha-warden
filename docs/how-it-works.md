# How it works

Home Assistant already has a permission engine. It checks every state read and every entity action call against a per-user policy. It has no way to configure that policy. Warden compiles each person's groups into a policy and gives it to Home Assistant, so Home Assistant enforces it, everywhere it already checks.

## What Warden does to users

- When someone joins their first group, Warden remembers their current role and replaces it with a personal Home Assistant auth group named `Warden: <user name>`, holding their compiled policy.
- When they leave their last group, they get their old role back.
- Members of an administrator group get the Home Assistant administrator group instead.
- Restricted people (2FA required, grace period over) get a policy that denies everything.
- The owner account is never managed.

Warden reconciles everyone at startup, every 5 minutes, and when users, the entity, device, area or label registries, or 2FA methods change. Policies that depend on the registries (labels, for example) are recompiled when the registries change.

## What is enforced

For managed users, by Home Assistant:

- Entity states over the websocket and REST APIs (the frontend, the app, long-lived tokens).
- Actions that target entities (`light.turn_on`, `lock.unlock` and so on), including calls that target a device or area.
- History.

By Warden:

- The sidebar: panels a person may not open are removed from the list the frontend receives.
- Dashboards: for a dashboard a person may not open, the dashboard's content request returns a placeholder explaining why.
- The default dashboard: a restricted person is given their first allowed dashboard.

Warden does this by wrapping the websocket commands `get_panels`, `lovelace/config`, `frontend/get_system_data` and `frontend/subscribe_system_data`.

## What is not covered

Home Assistant doesn't check entity permissions in these places:

- **Actions that don't target entities.** Calling `script.my_script` or `notify.mobile_app_x` directly isn't checked. Running a script as an entity (`script.turn_on` with a target) is. If a script does something sensitive, deny its entity and don't expose it as a plain action.
- **Logbook**, and registry listings. Device, area and entity names are visible, though not their states. Deny the Logbook panel if that matters.
- **Admin-only features** (settings, add-ons, developer tools) were never open to non-administrators and still aren't.

Deny is the strongest tool. For anything sensitive, deny it outright rather than relying on a narrower allow elsewhere.

## Unloading and removing

- Disabling, reloading or restarting keeps everyone's restrictions in place. Warden never widens access by being switched off. Dashboard and panel filtering pauses while it's disabled. Entity permissions stay.
- Deleting the integration gives every managed user their original role back and removes Warden's data. Do this before deleting the files.
