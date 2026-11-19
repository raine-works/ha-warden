"""Fixtures for the Warden tests."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.auth.mfa_modules import auth_mfa_module_from_config
from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.warden.const import DOMAIN
from custom_components.warden.manager import WardenManager

pytest_plugins = ("pytest_homeassistant_custom_component",)

CLIENT_ID = "https://example.com/app"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components/."""


@pytest.fixture
async def warden(hass: HomeAssistant, hass_owner_user: User) -> WardenManager:
    """Set up Warden and the frontend it depends on.

    This must run before any websocket client connects: starting the test
    server freezes the HTTP router, and the frontend registers routes.
    """
    entry = MockConfigEntry(domain=DOMAIN, title="Warden")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data


@pytest.fixture
def make_user(hass: HomeAssistant) -> Callable[..., Awaitable[User]]:
    """Create a regular (non-admin) user."""

    async def make(name: str = "Kid", group_ids: list[str] | None = None) -> User:
        return await hass.auth.async_create_user(
            name, group_ids=group_ids or [GROUP_ID_USER]
        )

    return make


@pytest.fixture
def user_ws(
    hass: HomeAssistant, hass_ws_client: Any
) -> Callable[[User], Awaitable[Any]]:
    """Open a websocket connection authenticated as the given user."""

    async def connect(user: User) -> Any:
        token = await hass.auth.async_create_refresh_token(user, CLIENT_ID)
        return await hass_ws_client(hass, hass.auth.async_create_access_token(token))

    return connect


@pytest.fixture
async def mfa_module(hass: HomeAssistant) -> str:
    """Load a 2FA module (the test harness has none by default).

    Request it before ``warden`` so Warden sees the module when it starts.
    """
    module = await auth_mfa_module_from_config(
        hass, {"type": "insecure_example", "data": []}
    )
    hass.auth._mfa_modules[module.id] = module
    return module.id


async def ws_call(client: Any, **msg: Any) -> Any:
    """Send a command and return its result, failing on an error."""
    await client.send_json_auto_id(msg)
    response = await client.receive_json()
    assert response["success"], response
    return response["result"]
