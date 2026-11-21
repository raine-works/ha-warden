# Compatibility

- Warden requires Home Assistant 2026.10 or newer (`hacs.json` sets `2026.10.0`).
- Warden depends on the `frontend`, `http`, `lovelace`, `panel_custom` and `websocket_api` integrations.
- It is a service integration with a single config entry. It has no devices or entities.

## The auth store bridge

Home Assistant stores custom permission groups in its auth data, but has no public API for creating them. Warden writes them through a small internal bridge, `custom_components/warden/auth_bridge.py`. The bridge checks those internals on startup and refuses to load, with an error, if they ever change, rather than guess.

User membership changes go through Home Assistant's public API.

## Wrapped websocket commands

Dashboard and panel access works by wrapping four of Home Assistant's frontend websocket commands. See [How it works](how-it-works.md#what-is-enforced).
