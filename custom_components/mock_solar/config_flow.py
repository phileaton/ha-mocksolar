"""UI configuration for a single local manual simulator."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_CREATE_DASHBOARD, CONFIG_VERSION, DOMAIN


class MockSolarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one simulator with a fixed entity contract."""

    VERSION = CONFIG_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004 HA flow interface
    ) -> MockSolarOptionsFlow:
        """Offer dashboard creation for existing simulator entries."""
        return MockSolarOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm creation; no credentials or external connection is needed."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title="Mock Solar",
                data={},
                options={
                    CONF_CREATE_DASHBOARD: user_input.get(CONF_CREATE_DASHBOARD, True)
                },
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_CREATE_DASHBOARD, default=True): bool}
            ),
        )


class MockSolarOptionsFlow(config_entries.OptionsFlow):
    """Enable optional dashboard creation without reloading simulation state."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Save the preference; existing dashboards are always preserved."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CREATE_DASHBOARD,
                        default=self.config_entry.options.get(
                            CONF_CREATE_DASHBOARD, False
                        ),
                    ): bool,
                }
            ),
        )
