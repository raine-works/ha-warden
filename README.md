<p align="center">
  <img src="custom_components/warden/brand/icon@2x.png" alt="Warden" width="128" />
</p>

# Warden for Home Assistant

Groups, fine-grained permissions and required two-factor authentication for
[Home Assistant](https://www.home-assistant.io/) users, from
[raine-works](https://github.com/raine-works).

Out of the box, Home Assistant users are either **administrators** or
**users**, and a user can see and control everything. Warden lets you put
people in groups and decide, per group, which entities, devices, areas,
dashboards and sidebar panels they can use, and whether they must use
two-factor authentication.

Warden compiles each person's groups into a policy and gives it to Home
Assistant, so the enforcement is Home Assistant's own. The owner account is
never managed or restricted, so there is always a way back in.

[![Home Assistant Marketplace](https://img.shields.io/badge/Home_Assistant-Marketplace-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=raine-works&repository=ha-warden&category=integration)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg?style=for-the-badge)](LICENSE)

[![Test](https://github.com/raine-works/ha-warden/actions/workflows/test.yaml/badge.svg)](https://github.com/raine-works/ha-warden/actions/workflows/test.yaml)
[![Validate](https://github.com/raine-works/ha-warden/actions/workflows/validate.yaml/badge.svg)](https://github.com/raine-works/ha-warden/actions/workflows/validate.yaml)

<a href="https://buymeacoffee.com/raineworks"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee" /></a>

## Features

- **Groups** with any number of members; a person can be in several groups.
- **Entity permissions** by entity, device, area, domain, label, or everything,
  at three levels: Read, Control and Deny. Deny always wins.
- **Dashboard and panel access**: pick which dashboards and sidebar pages a
  group can open.
- **Administrator groups**: members become Home Assistant administrators.
- **Required two-factor authentication**, for everyone or per group, with a
  grace period and a setup prompt for people who are already logged in.
- A **Warden** admin panel in the sidebar.

## Installation

Requires Home Assistant 2026.10 or newer.

[![Open your Home Assistant instance and open this repository in the Home Assistant Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=raine-works&repository=ha-warden&category=integration)

1. Click the button above, or open **Settings → Marketplace**. If Warden isn't
   listed, add `https://github.com/raine-works/ha-warden` as a custom
   repository with type **Integration**.
2. Download **Warden**, then restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Warden**.

You can also copy `custom_components/warden` into your `config/custom_components/`
folder by hand. See [Installation](docs/installation.md) for details.

## Documentation

| Guide | What it covers |
| :--- | :--- |
| [Installation](docs/installation.md) | Installing from the Home Assistant Marketplace or by hand, and removing Warden |
| [Setup](docs/setup.md) | Adding the integration and your first group |
| [Groups and permissions](docs/permissions.md) | Group settings, entity rules, dashboards, panels, administrators |
| [Two-factor authentication](docs/two-factor.md) | Requiring 2FA, the grace period, the setup prompt |
| [How it works](docs/how-it-works.md) | What Warden enforces and what it doesn't |
| [Troubleshooting](docs/troubleshooting.md) | Lockouts, repairs and startup errors |
| [Compatibility](docs/compatibility.md) | Home Assistant versions and the auth store bridge |
| [What Warden creates](docs/reference/created.md) | Panels, auth groups, storage and repairs |
| [Python and websocket API](docs/reference/api.md) | The read-only group API for other integrations |
| [Development](docs/development.md) | Setup, tests and releasing |

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
