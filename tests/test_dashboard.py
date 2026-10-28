"""Verify editable dashboard creation, preservation, regeneration and options."""

from typing import Any
from unittest.mock import patch

from homeassistant import auth
from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.mock_solar.const import CONF_CREATE_DASHBOARD, DOMAIN
from custom_components.mock_solar.dashboard import (
    DASHBOARD_PATH,
    DEFAULT_PATH,
    dashboard_collection,
)

from .helpers import HomeAssistantTestCase


def references(value: Any) -> set[str]:
    """Collect entity references from cards and nested action targets."""
    if isinstance(value, dict):
        return set().union(
            *(
                references(item)
                for key, item in value.items()
                if key not in {"perform_action", "service"}
            )
        )
    if isinstance(value, list):
        return set().union(*(references(item) for item in value))
    if isinstance(value, str) and value.startswith(
        ("sensor.", "number.", "switch.", "binary_sensor.", "button.")
    ):
        return {value}
    return set()


class DashboardTests(HomeAssistantTestCase):
    """Use the actual Lovelace collection and stored dashboard implementation."""

    async def asyncSetUp(self) -> None:
        """Initialize test authentication required by Lovelace's HTTP dependency."""
        await super().asyncSetUp()
        self.hass.auth = await auth.auth_manager_from_config(
            self.hass, [{"type": "homeassistant"}], []
        )

    async def test_creation_and_registry_ids(self) -> None:
        """The generated sidebar dashboard references native IDs, including suffixes."""
        self.hass.states.async_set("sensor.mock_grid_power", "123")
        entry = await self.create_simulator(create_dashboard=True)
        path = entry.data[DASHBOARD_PATH]
        self.assertTrue(frontend.async_panel_exists(self.hass, path))
        config = (
            await self.hass.data[LOVELACE_DATA].dashboards[path].async_load(force=False)
        )
        self.assertEqual(config["title"], "Mock Energy Lab")
        registry = er.async_get(self.hass)
        entities = er.async_entries_for_config_entry(registry, entry.entry_id)
        expected = {entity.entity_id for entity in entities}
        self.assertEqual(references(config), expected)
        self.assertNotIn("sensor.mock_grid_power", references(config))
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 123)
        self.assertEqual(len(dashboard_collection(self.hass).async_items()), 1)

    async def test_opt_out_does_not_load_lovelace(self) -> None:
        """An optional dashboard never becomes a simulator setup dependency."""
        await self.create_simulator()
        self.assertNotIn(LOVELACE_DATA, self.hass.data)
        with self.assertRaises(HomeAssistantError):
            await self.command("button", "press", "button.mock_regenerate_dashboard")
        self.assertNotIn(LOVELACE_DATA, self.hass.data)

    async def test_options_preserve_simulation_and_existing_dashboard(self) -> None:
        """Options enable creation without reload and never overwrite edits."""
        entry = await self.create_simulator()
        coordinator = entry.runtime_data
        await self.command("number", "set_value", "number.mock_solar_kw", value=1)
        form = await self.hass.config_entries.options.async_init(entry.entry_id)
        result = await self.hass.config_entries.options.async_configure(
            form["flow_id"], {CONF_CREATE_DASHBOARD: True}
        )
        self.assertEqual(result["type"], "create_entry")
        await self.hass.async_block_till_done()
        path = entry.data[DASHBOARD_PATH]
        dashboard = self.hass.data[LOVELACE_DATA].dashboards[path]
        config = await dashboard.async_load(force=False)
        config["title"] = "My customized energy lab"
        config["views"][0]["cards"].append({"type": "markdown", "content": "Keep me"})
        await dashboard.async_save(config)
        for enabled in (False, True):
            form = await self.hass.config_entries.options.async_init(entry.entry_id)
            await self.hass.config_entries.options.async_configure(
                form["flow_id"], {CONF_CREATE_DASHBOARD: enabled}
            )
            await self.hass.async_block_till_done()
            self.assertIs(entry.runtime_data, coordinator)
            self.assertEqual(self.number_value("sensor.mock_solar_power"), 1)
            self.assertEqual(await dashboard.async_load(force=False), config)
        self.assertTrue(await self.hass.config_entries.async_reload(entry.entry_id))
        await self.hass.async_block_till_done()
        self.assertEqual(entry.data[DASHBOARD_PATH], path)
        self.assertEqual(await dashboard.async_load(force=False), config)
        self.assertEqual(len(dashboard_collection(self.hass).async_items()), 1)

    async def test_regenerate_replaces_edits_and_resolves_renames(self) -> None:
        """The explicit regenerate button replaces the layout using current IDs."""
        entry = await self.create_simulator(create_dashboard=True)
        dashboard = self.hass.data[LOVELACE_DATA].dashboards[entry.data[DASHBOARD_PATH]]
        config = await dashboard.async_load(force=False)
        config["title"] = "Custom title"
        await dashboard.async_save(config)
        registry = er.async_get(self.hass)
        registry.async_update_entity(
            "sensor.mock_grid_power", new_entity_id="sensor.lab_grid"
        )
        await self.hass.async_block_till_done()
        await self.command("button", "press", "button.mock_regenerate_dashboard")
        rebuilt = await dashboard.async_load(force=False)
        self.assertEqual(rebuilt["title"], "Mock Energy Lab")
        self.assertIn("sensor.lab_grid", references(rebuilt))
        self.assertNotIn("sensor.mock_grid_power", references(rebuilt))
        self.assertEqual(len(dashboard_collection(self.hass).async_items()), 1)

    async def test_foreign_dashboard_collision_and_ownership(self) -> None:
        """A preexisting dashboard is never adopted or overwritten."""
        self.assertTrue(await async_setup_component(self.hass, "lovelace", {}))
        collection = dashboard_collection(self.hass)
        await collection.async_create_item(
            {"title": "Existing lab", "url_path": DEFAULT_PATH}
        )
        foreign = self.hass.data[LOVELACE_DATA].dashboards[DEFAULT_PATH]
        original = {"title": "My dashboard", "views": []}
        await foreign.async_save(original)
        entry = await self.create_simulator(create_dashboard=True)
        self.assertNotEqual(entry.data[DASHBOARD_PATH], DEFAULT_PATH)
        self.assertEqual(await foreign.async_load(force=False), original)
        managed = self.hass.data[LOVELACE_DATA].dashboards[entry.data[DASHBOARD_PATH]]
        # Losing the ownership marker must fail safely rather than erase content.
        await managed.async_save(original.copy())
        with self.assertRaises(HomeAssistantError):
            await self.command("button", "press", "button.mock_regenerate_dashboard")
        self.assertEqual(await managed.async_load(force=False), original)
        await entry.runtime_data.dashboard.async_ensure()
        self.assertEqual(await managed.async_load(force=False), original)

    async def test_failure_keeps_simulator_loaded_and_rolls_back_panel(self) -> None:
        """A failed dashboard save leaves no blank panel and does not break entities."""
        with (
            patch(
                "homeassistant.components.lovelace.dashboard.LovelaceStorage.async_save",
                side_effect=HomeAssistantError("Simulated storage failure"),
            ),
            self.assertLogs("custom_components.mock_solar", level="ERROR"),
        ):
            entry = await self.create_simulator(create_dashboard=True)
        self.assertNotIn(DASHBOARD_PATH, entry.data)
        self.assertFalse(frontend.async_panel_exists(self.hass, DEFAULT_PATH))
        self.assertEqual(self.number_value("sensor.mock_grid_power"), -4)
        self.assertEqual(dashboard_collection(self.hass).async_items(), [])

    async def test_removal_keeps_editable_dashboard(self) -> None:
        """Integration removal does not destroy user-editable dashboard content."""
        entry = await self.create_simulator(create_dashboard=True)
        path = entry.data[DASHBOARD_PATH]
        dashboard = self.hass.data[LOVELACE_DATA].dashboards[path]
        before = await dashboard.async_load(force=False)
        await self.hass.config_entries.async_remove(entry.entry_id)
        await self.hass.async_block_till_done()
        self.assertTrue(frontend.async_panel_exists(self.hass, path))
        self.assertEqual(await dashboard.async_load(force=False), before)

    async def test_setup_form_defaults_to_dashboard_creation(self) -> None:
        """New users see an explicit checked option; older entries stay opted out."""
        form = await self.hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        self.assertEqual(form["data_schema"]({}), {CONF_CREATE_DASHBOARD: True})
        result = await self.hass.config_entries.flow.async_configure(
            form["flow_id"], {}
        )
        await self.hass.async_block_till_done()
        self.assertTrue(result["result"].options[CONF_CREATE_DASHBOARD])
        self.assertIn(DASHBOARD_PATH, result["result"].data)
