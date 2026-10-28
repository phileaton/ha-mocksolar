"""UI configuration for a single local manual simulator."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .const import CONFIG_VERSION, DOMAIN


class MockSolarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one simulator with a fixed entity contract."""

    VERSION = CONFIG_VERSION

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm creation; no credentials or external connection is needed."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Mock Solar", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
