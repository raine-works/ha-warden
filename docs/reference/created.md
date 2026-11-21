# What Warden creates

Warden creates no entities, devices, events or actions.

## Sidebar panels

| Panel | Path | Who sees it |
| :--- | :--- | :--- |
| Warden | `warden` | Administrators |
| Account security | `warden-security` | Everyone, but hidden from people who don't need to set up 2FA |

## Frontend script

A script served from `/warden_static/warden-prompt.js` runs on every page. It prompts logged-in users when 2FA becomes required. See [Two-factor authentication](../two-factor.md).

## Auth groups

Every managed user gets one Home Assistant auth group, with the id `warden-<user id>` and the name `Warden: <user name>`, holding their compiled policy. Unused ones are removed.

## Storage

Groups, settings and per-user records are in Home Assistant's `.storage/warden` file. For each user it keeps their original groups, when 2FA first became required and the groups Warden last applied.

## Repairs

| Issue | When |
| :--- | :--- |
| Two-factor authentication can't be enforced | 2FA is required but no 2FA module is loaded |
