# Setup

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=warden)

## Add the integration

1. Click the button above, or go to **Settings → Devices & services → Add integration → Warden**.
2. Read the description and confirm.

The setup has one step and no options. Only one Warden entry is allowed; adding it again aborts with "Warden is already set up". Everything else is configured in the Warden panel.

The owner account is never restricted, so you can't lock yourself out with this step.

## The Warden panel

After setup, **Warden** appears in the sidebar for administrators. Use it to:

- create groups and add members
- set each group's entity, dashboard and panel access
- mark a group as administrators
- require two-factor authentication, for a group or for everyone

A second sidebar page, **Account security**, appears only for people who still have to set up 2FA.

## Your first group

1. Open **Warden** and create a group.
2. Add members. The owner and system users can't be added.
3. Add entity rules, and pick the dashboards and panels the group can open. See [Groups and permissions](permissions.md).
4. Optionally require 2FA. See [Two-factor authentication](two-factor.md).

When someone joins their first group, Warden replaces their role with a personal policy built from their groups. When they leave their last group, they get their old role back.

## Global settings

Two settings apply to everyone except the owner. They are on the **Two-factor** tab.

| Setting | Meaning | Default |
| :--- | :--- | :--- |
| Require two-factor authentication for everyone | Requires 2FA for every user, in a group or not | Off |
| Grace period (days) | Days a person can keep using Home Assistant before they must enroll. 0 to 365. 0 means immediately | 7 |
