"""Shared real Home Assistant harness for local and upstream contract tests."""

import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


class HomeAssistantTestCase(unittest.IsolatedAsyncioTestCase):
    """Run the real platforms with a fresh temporary HA configuration."""

    async def asyncSetUp(self) -> None:
        """Initialize Home Assistant's registries and service infrastructure."""
        self.directory = TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config.skip_pip = True
        loader.async_setup(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.assertTrue(await async_load_base_functionality(self.hass))
        self.assertTrue(await async_setup_component(self.hass, "homeassistant", {}))
        self.no_network = patch(
            "aiohttp.ClientSession._request",
            side_effect=AssertionError("Unexpected network request"),
        )
        self.no_network.start()

    async def asyncTearDown(self) -> None:
        """Stop HA and remove all temporary registry/configuration files."""
        await self.hass.async_stop()
        self.no_network.stop()
        self.directory.cleanup()

    async def create_simulator(self, *, create_dashboard: bool = False) -> ConfigEntry:
        """Create and load the integration through its actual user flow."""
        form = await self.hass.config_entries.flow.async_init(
            "mock_solar", context={"source": "user"}
        )
        self.assertEqual(form["type"], "form")
        result = await self.hass.config_entries.flow.async_configure(
            form["flow_id"], {"create_dashboard": create_dashboard}
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"], {})
        await self.hass.async_block_till_done()
        entry = result["result"]
        self.assertEqual(entry.state, ConfigEntryState.LOADED)
        return entry

    def number_value(self, entity_id: str) -> float:
        """Read a numeric state while failing on missing or unavailable outputs."""
        state = self.hass.states.get(entity_id)
        self.assertIsNotNone(state, entity_id)
        return float(state.state)

    async def command(
        self, domain: str, service: str, entity_id: str, **data: float
    ) -> None:
        """Send the same services external integrations and dashboards use."""
        await self.hass.services.async_call(
            domain, service, {"entity_id": entity_id, **data}, blocking=True
        )
        await self.hass.async_block_till_done()
