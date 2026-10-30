"""Exercise actual Home Assistant setup, services, registry and unload."""

from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry

from .helpers import HomeAssistantTestCase


class IntegrationTests(HomeAssistantTestCase):
    """Verify the local integration against actual HA services and registries."""

    async def test_setup_metadata_and_single_instance(self) -> None:
        """Default entity IDs, classes and unique identities survive real setup."""
        entry = await self.create_simulator()
        registry = entity_registry.async_get(self.hass)
        entities = entity_registry.async_entries_for_config_entry(
            registry, entry.entry_id
        )
        self.assertEqual(len(entities), 40)
        self.assertEqual(len({e.unique_id for e in entities}), 40)
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 0)
        self.assertEqual(self.number_value("sensor.mock_ev_battery_soc"), 50)
        for entity_id, device_class, unit in (
            ("sensor.mock_solar_power", "power", "kW"),
            ("sensor.mock_ev_battery_soc", "battery", "%"),
        ):
            state = self.hass.states.get(entity_id)
            self.assertEqual(state.attributes["device_class"], device_class)
            self.assertEqual(state.attributes["unit_of_measurement"], unit)
            self.assertEqual(state.attributes["state_class"], "measurement")
        result = await self.hass.config_entries.flow.async_init(
            "mock_solar", context={"source": "user"}
        )
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "single_instance_allowed")

    async def test_external_charger_commands(self) -> None:
        """Current and switch services immediately update every dependent output."""
        await self.create_simulator()
        await self.command("switch", "turn_on", "switch.mock_charger_charge_control")
        self.assertEqual(self.number_value("sensor.mock_charger_power"), 0)
        await self.command(
            "number", "set_value", "number.mock_charger_session_current_limit", value=10
        )
        self.assertEqual(self.number_value("sensor.mock_charger_power"), 2.4)
        self.assertEqual(self.number_value("sensor.mock_home_load"), 4.4)
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 0)
        self.assertEqual(self.number_value("sensor.mock_battery_power"), -3.6)
        self.assertEqual(
            self.hass.states.get("sensor.mock_charger_state").state, "charger_charging"
        )
        await self.command(
            "number", "set_value", "number.mock_charger_maximum_current", value=6
        )
        self.assertEqual(self.number_value("sensor.mock_charger_power"), 1.44)
        await self.command(
            "number", "set_value", "number.mock_charger_session_current_limit", value=5
        )
        self.assertEqual(self.number_value("sensor.mock_charger_power"), 0)
        self.assertEqual(
            self.hass.states.get("sensor.mock_charger_status_connector").state,
            "SuspendedEVSE",
        )
        await self.command("switch", "turn_on", "switch.mock_charger_force_finishing")
        self.assertEqual(
            self.hass.states.get("sensor.mock_charger_state").state, "charger_end"
        )
        await self.command("switch", "turn_off", "switch.mock_charger_connected")
        self.assertEqual(
            self.hass.states.get("sensor.mock_charger_state").state, "charger_free"
        )
        self.assertEqual(
            self.hass.states.get("binary_sensor.mock_ev_connected").state, "off"
        )
        await self.command("switch", "turn_off", "switch.mock_charger_charge_control")
        self.assertEqual(
            self.hass.states.get("switch.mock_charger_charge_control").state, "off"
        )

    async def test_battery_and_grid_follow_production_and_load(self) -> None:
        """Battery and grid are derived; invalid services leave state untouched."""
        await self.create_simulator()
        await self.command("number", "set_value", "number.mock_house_kw", value=10)
        self.assertEqual(self.number_value("sensor.mock_battery_power"), 2)
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 0)
        await self.command("number", "set_value", "number.mock_solar_kw", value=20)
        self.assertEqual(self.number_value("sensor.mock_battery_power"), -10)
        await self.command("number", "set_value", "number.mock_house_kw", value=0)
        self.assertEqual(self.number_value("sensor.mock_battery_power"), -12)
        self.assertEqual(self.number_value("sensor.mock_grid_power"), -8)
        await self.command(
            "number", "set_value", "number.mock_ev_soc_setting", value=100
        )
        self.assertEqual(self.number_value("sensor.mock_ev_battery_soc"), 100)
        for value in (-1, 101, float("nan")):
            with self.subTest(value=value), self.assertRaises(HomeAssistantError):
                await self.command(
                    "number", "set_value", "number.mock_ev_soc_setting", value=value
                )
        self.assertEqual(self.number_value("sensor.mock_ev_battery_soc"), 100)

    async def test_unload_and_reload(self) -> None:
        """Subscriptions are cleaned up; IDs survive reload with repeatable defaults."""
        entry = await self.create_simulator()
        original_ids = {s.entity_id for s in self.hass.states.async_all()}
        coordinator = entry.runtime_data
        await self.command("homeassistant", "update_entity", "sensor.mock_grid_power")
        await self.command("number", "set_value", "number.mock_solar_kw", value=0)
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 0)
        self.assertEqual(self.number_value("sensor.mock_battery_power"), 2)
        self.assertTrue(coordinator._listeners)  # noqa: SLF001 Verify subscription cleanup
        self.assertTrue(await self.hass.config_entries.async_unload(entry.entry_id))
        await self.hass.async_block_till_done()
        self.assertFalse(coordinator._listeners)  # noqa: SLF001 Verify subscription cleanup
        self.assertEqual(
            self.hass.states.get("sensor.mock_solar_power").state, "unavailable"
        )
        self.assertTrue(await self.hass.config_entries.async_setup(entry.entry_id))
        await self.hass.async_block_till_done()
        self.assertEqual(
            {s.entity_id for s in self.hass.states.async_all()}, original_ids
        )
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 0)

    async def test_blueprint_entry_migration(self) -> None:
        """Existing sample entries lose obsolete credentials and load local entities."""
        entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain="mock_solar",
            title="old-user",
            data={"username": "old-user", "password": "sample"},
            options={},
            source="user",
            unique_id="old-user",
            discovery_keys=MappingProxyType({}),
            subentries_data=(),
        )
        await self.hass.config_entries.async_add(entry)
        await self.hass.async_block_till_done()
        self.assertEqual(entry.state, ConfigEntryState.LOADED)
        self.assertEqual(entry.version, 2)
        self.assertEqual(dict(entry.data), {})
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 0)

    async def test_existing_entity_id_is_not_overwritten(self) -> None:
        """Keep an occupied legacy ID and assign the native entity a suffix."""
        self.hass.states.async_set("sensor.mock_grid_power", "123")
        entry = await self.create_simulator()
        self.assertEqual(self.number_value("sensor.mock_grid_power"), 123)
        registry = entity_registry.async_get(self.hass)
        assigned = registry.async_get_entity_id(
            "sensor", "mock_solar", f"{entry.entry_id}_grid_power"
        )
        self.assertNotEqual(assigned, "sensor.mock_grid_power")
        self.assertEqual(self.number_value(assigned), 0)

    async def test_compatibility_outputs_follow_commands(self) -> None:
        """Adapters preserve kW telemetry and update watts/signs with each command."""
        await self.create_simulator()
        expected = {
            "solar_power_w": 8000,
            "house_load_w": 2000,
            "home_load_w": 2000,
            "grid_power_w": 0,
            "charger_power_w": 0,
            "battery_power_charge_positive_w": 6000,
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                state = self.hass.states.get(f"sensor.mock_{key}")
                self.assertEqual(float(state.state), value)
                self.assertEqual(state.attributes["unit_of_measurement"], "W")
                self.assertEqual(state.attributes["device_class"], "power")
                self.assertEqual(state.attributes["state_class"], "measurement")
        await self.command("number", "set_value", "number.mock_solar_kw", value=0)
        self.assertEqual(self.number_value("sensor.mock_battery_power"), 2)
        self.assertEqual(
            self.number_value("sensor.mock_battery_power_charge_positive_w"), -2000
        )
        await self.command("switch", "turn_on", "switch.mock_charger_charge_control")
        await self.command(
            "number", "set_value", "number.mock_charger_session_current_limit", value=16
        )
        self.assertEqual(self.number_value("sensor.mock_charger_power_w"), 3840)
        self.assertEqual(self.number_value("sensor.mock_home_load_w"), 5840)
        self.assertEqual(self.number_value("sensor.mock_house_load_w"), 2000)
        self.assertEqual(
            self.number_value("sensor.mock_battery_power_charge_positive_w"), -5840
        )
        self.assertEqual(self.number_value("sensor.mock_grid_power_w"), 0)
        await self.command("switch", "turn_off", "switch.mock_charger_charge_control")
        self.assertEqual(self.number_value("sensor.mock_charger_power_w"), 0)
