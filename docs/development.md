# Development

## Setup and checks

```bash
uv venv .venv   # uses the exact Python pinned in .python-version
uv pip install -p .venv -r requirements-test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest -q
```

The Python release is pinned in `.python-version`. Change it on purpose, in a change of its own.

The tests run Warden inside a real Home Assistant and check access through Home Assistant's own permission engine. They live in `tests/`.

## Layout

| File | Role |
| :--- | :--- |
| `custom_components/warden/__init__.py` | Setup, unload, removal, panels and the prompt script |
| `config_flow.py` | The one-step setup |
| `manager.py` | Reconciles users with groups and 2FA rules |
| `policy.py` | Compiles entity rules into a Home Assistant policy |
| `auth_bridge.py` | Everything that touches the auth store's internals |
| `guards.py` | Dashboard and panel enforcement |
| `websocket_api.py` | Commands behind the panels |
| `api.py` | The read-only API for other integrations |
| `store.py`, `models.py` | Storage and data model |
| `frontend/` | The admin panel and the setup prompt |

## Contributing

Issues and pull requests are welcome. This is a community project maintained on a best-effort basis.

## Releasing

The `Test` workflow runs ruff and pytest. When it passes on a push to `master`, the `Release` workflow reads `version` from `custom_components/warden/manifest.json`. If a release with the tag `v<version>` doesn't exist, it creates one with generated notes. Don't change that version by hand: on every push to `master`, the `Release pull request` workflow keeps one pull request, `Release v<version>`, open with the next version (major for a breaking change, `type!:`; minor for a `feat`; patch for anything else that changes `custom_components/`), and its `## Unreleased` changelog entries under that version. To release, merge it. A change that users would notice adds its entry to [CHANGELOG.md](../CHANGELOG.md) under `## Unreleased`. The `Validate` workflow runs hassfest and the Marketplace validation.
