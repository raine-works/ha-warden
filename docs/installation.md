# Installation

Warden needs Home Assistant 2026.10 or newer.

## Home Assistant Marketplace (recommended)

[![Open your Home Assistant instance and open this repository in the Home Assistant Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=raine-works&repository=ha-warden&category=integration)

1. Open the Marketplace with the button above, or go to **Settings → Marketplace**.
2. If Warden isn't listed, add `https://github.com/raine-works/ha-warden` as a custom repository with type **Integration**.
3. Download **Warden**.
4. Restart Home Assistant.

## Manual

1. Copy the `custom_components/warden` folder from this repository into your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Next step

[Set up Warden](setup.md).

## Removing Warden

Delete the integration before you delete its files. Go to **Settings → Devices & services → Warden → Delete**. This gives every managed user their original role back and removes Warden's data. If you delete the files first, managed users keep their Warden policy.

Disabling, reloading or restarting Warden does not widen anyone's access. See [How it works](how-it-works.md#unloading-and-removing).
