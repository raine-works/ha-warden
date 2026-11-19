"""Config flow for Warden."""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class WardenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add Warden. Everything else is set up in the Warden panel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup."""
        if user_input is not None:
            return self.async_create_entry(title="Warden", data={})
        return self.async_show_form(step_id="user")
