"""Optional contract checks using an external EV Smart Charger source checkout."""

import importlib
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from .helpers import HomeAssistantTestCase

EVSC_SOURCE = os.environ.get("MOCK_SOLAR_EVSC_PATH")


def load_upstream() -> tuple[ModuleType, ModuleType, ModuleType]:
    """Load real upstream submodules without installing its full integration."""
    source = Path(EVSC_SOURCE)
    if (source / "custom_components" / "ev_smart_charger").is_dir():
        source = source / "custom_components" / "ev_smart_charger"
    # Bypass upstream __init__, which initializes dashboards and scheduling.
    # Relative imports still load the unmodified upstream modules from disk.
    package = ModuleType("_mocksolar_evsc_contract")
    package.__path__ = [str(source)]
    sys.modules[package.__name__] = package
    return tuple(
        importlib.import_module(f"{package.__name__}.{name}")
        for name in ("power_model", "charger_controller", "runtime")
    )


UPSTREAM = load_upstream() if EVSC_SOURCE else None


@unittest.skipUnless(EVSC_SOURCE, "Set MOCK_SOLAR_EVSC_PATH to an upstream checkout")
class EVSmartChargerContractTests(HomeAssistantTestCase):
    """Verify upstream power readers and commands against real simulator entities."""

    async def test_upstream_readers_and_controller(self) -> None:
        """Read W/sign adapters, start, reduce current, suspend and stop charging."""
        entry = await self.create_simulator()
        power_module, controller_module, runtime_module = UPSTREAM
        config = {
            "phase_mode": "single",
            "charger_model": "generic",
            "fv_production": "sensor.mock_solar_power_w",
            "home_consumption": "sensor.mock_home_base_load_w",
            "grid_import": "sensor.mock_grid_power_w",
            "battery_power": "sensor.mock_battery_power_charge_positive_w",
            "charging_power": "sensor.mock_charger_power_w",
            "ev_charger_status": "sensor.mock_charger_state",
            "ev_charger_switch": "switch.mock_charger_charge_control",
            "ev_charger_current": "number.mock_charger_session_current_limit",
        }
        model = power_module.ChargingModel.from_config(config)
        runtime = runtime_module.EVSCRuntimeData(
            config=config, expected_entity_count=0, power_model=model
        )
        controller = controller_module.ChargerController(
            self.hass, entry.entry_id, config, runtime
        )
        await controller.async_setup()
        self.assertEqual(model.read_production(self.hass), 8000)
        self.assertEqual(model.read_consumption(self.hass), 2000)
        self.assertEqual(model.read_grid_import(self.hass), -4000)
        self.assertEqual(model.read_battery_discharge(self.hass), 0)
        self.assertFalse(model.is_charging(self.hass))
        # Omit intentional upstream hardware settling delays, retaining its real
        # command paths, services, state reads and current normalization.
        with patch.multiple(
            controller_module,
            CHARGER_AMPERAGE_STABILIZATION_DELAY=0,
            CHARGER_START_SEQUENCE_DELAY=0,
            CHARGER_STOP_SEQUENCE_DELAY=0,
            CHARGER_COMMAND_DELAY=0,
            CHARGER_MIN_OPERATION_INTERVAL=0,
        ):
            result = await controller.start_charger(16, "Mock Solar contract test")
            self.assertTrue(result.success, result.error_message)
            await self.hass.async_block_till_done()
            self.assertEqual(model.read_charging_power(self.hass), 3840)
            self.assertTrue(model.is_charging(self.hass))
            self.assertEqual(model.read_consumption(self.hass), 2000)
            self.assertEqual(self.number_value("sensor.mock_home_load_w"), 5840)
            self.assertEqual(model.read_grid_import(self.hass), -160)
            result = await controller.set_amperage(6, "Reduce current")
            self.assertTrue(result.success, result.error_message)
            await self.hass.async_block_till_done()
            self.assertEqual(model.read_charging_power(self.hass), 1440)
            # Exercise the actual upstream solar-surplus amperage helper with a
            # lower production reading, without enabling its scheduler.
            await self.command("number", "set_value", "number.mock_solar_kw", value=2)
            self.assertEqual(model.read_grid_import(self.hass), 3440)
            surplus = model.read_production(self.hass) - model.read_consumption(
                self.hass
            )
            calculator = importlib.import_module(
                "_mocksolar_evsc_contract.utils.amperage_helper"
            ).AmperageCalculator
            amps, _ = calculator.calculate_from_surplus(
                surplus,
                current_amps=6,
                amp_levels=model.amp_levels,
                voltage=model.effective_voltage,
            )
            self.assertEqual(amps, 0)
            result = await controller.stop_charger("Insufficient surplus")
            self.assertTrue(result.success, result.error_message)
            await self.hass.async_block_till_done()
            self.assertEqual(model.read_charging_power(self.hass), 0)
            self.assertFalse(model.is_charging(self.hass))
            await self.command("number", "set_value", "number.mock_solar_kw", value=8)
            result = await controller.start_charger(10, "Solar recovery")
            self.assertTrue(result.success, result.error_message)
            await self.hass.async_block_till_done()
            self.assertEqual(model.read_charging_power(self.hass), 2400)
            await self.command("number", "set_value", "number.mock_battery_kw", value=2)
            self.assertEqual(model.read_battery_discharge(self.hass), 2000)
            await self.command(
                "switch", "turn_on", "switch.mock_charger_force_finishing"
            )
            self.assertTrue(
                power_module.is_charge_complete_status(
                    self.hass.states.get("sensor.mock_charger_state").state
                )
            )
            self.assertFalse(model.is_charging(self.hass))
            await self.command("switch", "turn_off", "switch.mock_charger_connected")
            self.assertTrue(
                power_module.is_disconnected_status(
                    self.hass.states.get("sensor.mock_charger_state").state
                )
            )
            self.assertEqual(model.read_charging_power(self.hass), 0)
