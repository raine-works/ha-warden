# Warden documentation

![Warden](images/warden-icon.png)

Warden adds groups, fine-grained permissions and required two-factor authentication to Home Assistant.

| Guide | What it covers |
| :--- | :--- |
| [Installation](installation.md) | Installing from the Home Assistant Marketplace or by hand, and removing Warden |
| [Setup](setup.md) | Adding the integration and your first group |
| [Groups and permissions](permissions.md) | Group settings, entity rules, dashboards, panels, administrators |
| [Two-factor authentication](two-factor.md) | Requiring 2FA, the grace period, the setup prompt |
| [How it works](how-it-works.md) | What Warden does to users, what it enforces and what it doesn't |
| [Troubleshooting](troubleshooting.md) | Lockouts, repairs and startup errors |
| [Compatibility](compatibility.md) | Home Assistant versions and the auth store bridge |
| [Development](development.md) | Setting up, linting, testing and releasing |

| Reference | What it covers |
| :--- | :--- |
| [What Warden creates](reference/created.md) | Panels, auth groups, storage, repairs and the frontend script |
| [Python and websocket API](reference/api.md) | The read-only group API for other integrations and the panel's websocket commands |
