# Two-factor authentication

Turn on **Require two-factor authentication** in a group, or for everyone on the **Two-factor** tab, and set a grace period. 0 days means immediately.

## States

| State | Meaning |
| :--- | :--- |
| Exempt | 2FA isn't required for the person |
| Grace period | Required, not set up yet. Full access, with a reminder and an **Account security** page showing the deadline |
| Restricted | Grace period over. No entities, dashboards or panels except their profile, where they can set up 2FA. Administrators lose admin rights until they enroll |
| Compliant | 2FA set up. Normal access |
| Unenforceable | Required, but no 2FA module is loaded. Nobody is restricted |

The owner is always exempt.

## The setup prompt

When 2FA becomes required for someone, even if they're already logged in, a dialog opens on whatever page they have open. It walks them through scanning a QR code with an authenticator app and entering the code.

- During the grace period they can choose **Later**. They're asked again next session.
- Once restricted, the dialog stays until they've set it up or log out.
- When they finish, their access comes back straight away.

## The grace clock

The clock starts the first time a requirement applies to someone. It keeps running after they enroll, so turning 2FA off later and on again restricts them right away rather than giving a fresh grace period. If the requirement is removed, the clock resets.

Warden rechecks every 5 minutes, so a grace period that ends takes effect within that time. It also reacts at once when someone sets up or removes a 2FA method.

## Authentication modules

Home Assistant's built-in **Authenticator app** (TOTP) module is loaded by default. If you've changed `auth_mfa_modules` so that no module is available, Warden raises a repair and doesn't restrict anyone. See [Troubleshooting](troubleshooting.md#two-factor-authentication-cant-be-enforced).
