# Agent guidance for ha-warden

## Raineworks base rules

This repository follows Raineworks' base rules, in [`.raineworks/base.md`](.raineworks/base.md): read them before
changing anything. They're a copy of `base.md` in `raine-works/agents`, kept current by its sync: change them there,
not here. Where this file is more specific, it wins.

@.raineworks/base.md

## This repository

Warden is a Home Assistant custom integration (`custom_components/warden`): groups, per-group entity, dashboard and
panel permissions, and required two-factor authentication. It compiles each person's groups into a policy that Home
Assistant itself enforces; the owner account is never managed or restricted. Layout and file roles:
[docs/development.md](docs/development.md); design: [docs/how-it-works.md](docs/how-it-works.md).

- **Check:** `ruff check .`, `ruff format --check .` and `pytest -q` (Python pinned in `.python-version`, `requirements-test.txt`); the `Test`
  workflow runs them, and `Validate` runs hassfest and the Marketplace (HACS) validation.
- **Release:** bump `version` in `custom_components/warden/manifest.json` in the pull request. When `Test` passes on
  `master`, the `Release` workflow creates the GitHub release `v<version>` if the tag is new. Never tag by hand.
- **Deny always wins**, from any group and at any scope. Never weaken that, and never let the owner or system users be
  members of, or restricted by, a group.
- Everything that touches Home Assistant's auth store internals stays in `auth_bridge.py`; dashboard and panel
  enforcement is in `guards.py`, the policy in `policy.py`.
- Access-control and 2FA changes need tests in `tests/` that run inside a real Home Assistant (the denied path too).
- Documentation for users is in `docs/` and the README's table; update both with behaviour.
