"""Deterministic elapsed-time and energy-boundary tests for dynamic simulation."""

import asyncio
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from homeassistant.core import callback

from custom_components.mock_solar.simulation import SimulationState

from .helpers import HomeAssistantTestCase

if TYPE_CHECKING:
    from homeassistant.core import Event


class DynamicModelTests(unittest.TestCase):
    """Check stored energy, accelerated time and completion independently of HA."""

    def test_ev_energy_and_efficiency(self) -> None:
        """One hour at 3.84 kW stores 3.648 kWh at 95 percent efficiency."""
        state = SimulationState(
            dynamic_enabled=True,
            charger_enabled=True,
            charger_session_amps_setting=16,
        )
        advanced = state.advance(3600)
        self.assertAlmostEqual(advanced.ev_soc_setting, 54.56)
        stored = (
            (advanced.ev_soc_setting - state.ev_soc_setting)
            / 100
            * state.ev_capacity_kwh
        )
        self.assertAlmostEqual(stored, state.charger_power * 0.95)
        self.assertEqual(state.ev_soc_setting, 50)

    def test_battery_energy_and_boundaries(self) -> None:
        """Battery flow stops at empty/full without losing the requested power."""
        state = SimulationState(
            dynamic_enabled=True,
            battery_capacity_kwh=10,
            battery_soc_setting=50,
            solar_kw=0,
            house_kw=2,
        )
        discharge = state.advance(3600)
        self.assertEqual(discharge.battery_soc_setting, 30)
        self.assertEqual((50 - discharge.battery_soc_setting) / 100 * 10, 2)
        empty = state.advance(3600 * 100)
        self.assertEqual(empty.battery_soc_setting, 0)
        self.assertEqual(empty.battery_power, 0)
        self.assertEqual(empty.grid_power, 2)
        self.assertEqual(empty.advance(3600).battery_soc_setting, 0)
        charge = replace(state, solar_kw=4).advance(3600)
        self.assertEqual(charge.battery_soc_setting, 70)
        full = replace(state, solar_kw=4).advance(3600 * 100)
        self.assertEqual(full.battery_soc_setting, 100)
        self.assertEqual(full.battery_power, 0)
        self.assertLess(
            replace(full, solar_kw=0).advance(60).battery_soc_setting, 100
        )
        self.assertGreater(
            replace(empty, solar_kw=4).advance(60).battery_soc_setting, 0
        )

    def test_target_completion_and_resume(self) -> None:
        """Targets stop power immediately; raising the target permits a new session."""
        state = SimulationState(
            dynamic_enabled=True,
            charger_enabled=True,
            charger_session_amps_setting=16,
            ev_soc_setting=79.9,
        )
        done = state.advance(3600)
        self.assertEqual(done.ev_soc_setting, 80)
        self.assertEqual(done.charger_power, 0)
        self.assertEqual(done.charger_state, "charger_end")
        self.assertEqual(done.charger_status_connector, "Finishing")
        self.assertEqual(done.advance(3600).ev_soc_setting, 80)
        self.assertEqual(
            replace(done, charger_connected=False).charger_state, "charger_free"
        )
        resumed = replace(done, ev_target_soc=90)
        self.assertEqual(resumed.charger_state, "charger_charging")
        self.assertGreater(resumed.advance(60).ev_soc_setting, 80)
        above_target = replace(done, ev_soc_setting=90)
        self.assertEqual(above_target.advance(3600).ev_soc_setting, 90)
        self.assertEqual(replace(done, dynamic_enabled=False).charger_power, 3.84)

    def test_time_scaling_and_partitioning(self) -> None:
        """Accelerated and subdivided intervals produce the same bounded SOC."""
        state = SimulationState(
            dynamic_enabled=True,
            charger_enabled=True,
            charger_session_amps_setting=16,
        )
        accelerated = replace(state, simulation_speed=60).advance(60)
        self.assertAlmostEqual(
            accelerated.ev_soc_setting, state.advance(3600).ev_soc_setting
        )
        self.assertAlmostEqual(
            accelerated.battery_soc_setting, state.advance(3600).battery_soc_setting
        )
        split = state
        for _ in range(100):
            split = split.advance(3600)
        one_interval = state.advance(3600 * 100)
        self.assertEqual(split.ev_soc_setting, one_interval.ev_soc_setting)
        self.assertEqual(split.battery_soc_setting, one_interval.battery_soc_setting)

    def test_manual_and_blocked_charger_do_not_advance_ev(self) -> None:
        """Manual mode freezes both SOCs; zero draw never adds EV energy."""
        manual = SimulationState(charger_enabled=True, charger_session_amps_setting=16)
        self.assertEqual(manual.advance(3600), manual)
        for changes in (
            {"charger_enabled": False},
            {"charger_connected": False},
            {"charger_force_finishing": True},
            {"charger_session_amps_setting": 5},
        ):
            with self.subTest(changes=changes):
                state = replace(manual, dynamic_enabled=True, **changes)
                self.assertEqual(state.advance(3600).ev_soc_setting, 50)
        self.assertEqual(
            replace(manual, battery_soc_setting=0, solar_kw=0).battery_power, 0
        )

    def test_invalid_time_and_dynamic_parameters(self) -> None:
        """No invalid duration, capacity or speed can enter the energy model."""
        for elapsed in (-1, float("nan"), float("inf"), True, "60"):
            with self.subTest(elapsed=elapsed), self.assertRaises(ValueError):
                SimulationState().advance(elapsed)
        for key, value in (
            ("battery_capacity_kwh", 0),
            ("ev_capacity_kwh", 0),
            ("ev_charging_efficiency", 0),
            ("ev_charging_efficiency", 101),
            ("ev_target_soc", -1),
            ("ev_target_soc", 101),
            ("simulation_speed", 0),
            ("simulation_speed", 3601),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                SimulationState().with_input(key, value=value)


class DynamicIntegrationTests(HomeAssistantTestCase):
    """Control real HA entities with synthetic monotonic time and timer callbacks."""

    async def test_elapsed_commands_pause_and_speed(self) -> None:
        """Settle old power/speed before edits and exclude time spent paused."""
        with (
            patch(
                "custom_components.mock_solar.coordinator.monotonic", return_value=0
            ) as clock,
            patch(
                "custom_components.mock_solar.coordinator.async_track_time_interval"
            ) as scheduler,
        ):
            cancel = Mock()
            scheduler.return_value = cancel
            await self.create_simulator()
            await self.command(
                "number",
                "set_value",
                "number.mock_charger_session_current_limit",
                value=16,
            )
            await self.command(
                "switch", "turn_on", "switch.mock_charger_charge_control"
            )
            await self.command("switch", "turn_on", "switch.mock_dynamic_enabled")
            scheduler.assert_called_once()
            tick = scheduler.call_args.args[1]
            clock.return_value = 60
            await self.command(
                "number", "set_value", "number.mock_simulation_speed", value=60
            )
            self.assertAlmostEqual(
                self.number_value("sensor.mock_ev_battery_soc"), 50.076
            )
            clock.return_value = 120
            tick(datetime.now(UTC))
            await self.hass.async_block_till_done()
            self.assertAlmostEqual(
                self.number_value("sensor.mock_ev_battery_soc"), 54.636
            )
            clock.return_value = 150
            await self.command(
                "switch", "turn_off", "switch.mock_charger_charge_control"
            )
            self.assertAlmostEqual(
                self.number_value("sensor.mock_ev_battery_soc"), 56.916
            )
            clock.return_value = 180
            await self.command("switch", "turn_off", "switch.mock_dynamic_enabled")
            cancel.assert_called_once()
            clock.return_value = 10000
            await self.command("switch", "turn_on", "switch.mock_dynamic_enabled")
            self.assertAlmostEqual(
                self.number_value("sensor.mock_ev_battery_soc"), 56.916
            )
            self.assertEqual(scheduler.call_count, 2)
            tick(datetime.now(UTC))
            await self.hass.async_block_till_done()
            self.assertAlmostEqual(
                self.number_value("sensor.mock_ev_battery_soc"), 56.916
            )

    async def test_boundaries_reset_and_unload_cancel_timer(self) -> None:
        """Actual telemetry respects bounds and reset/unload cancel scheduled work."""
        with (
            patch(
                "custom_components.mock_solar.coordinator.monotonic", return_value=0
            ) as clock,
            patch(
                "custom_components.mock_solar.coordinator.async_track_time_interval"
            ) as scheduler,
        ):
            cancel = Mock()
            scheduler.return_value = cancel
            entry = await self.create_simulator()
            await self.command(
                "number", "set_value", "number.mock_battery_capacity_kwh", value=10
            )
            await self.command(
                "number", "set_value", "number.mock_battery_soc_setting", value=1
            )
            await self.command(
                "number", "set_value", "number.mock_ev_soc_setting", value=79
            )
            await self.command(
                "number", "set_value", "number.mock_simulation_speed", value=3600
            )
            await self.command(
                "number",
                "set_value",
                "number.mock_charger_session_current_limit",
                value=16,
            )
            await self.command(
                "switch", "turn_on", "switch.mock_charger_charge_control"
            )
            await self.command("number", "set_value", "number.mock_solar_kw", value=0)
            await self.command("number", "set_value", "number.mock_house_kw", value=12)
            await self.command("switch", "turn_on", "switch.mock_dynamic_enabled")
            tick = scheduler.call_args.args[1]
            clock.return_value = 1
            tick(datetime.now(UTC))
            await self.hass.async_block_till_done()
            self.assertEqual(self.number_value("sensor.mock_ev_battery_soc"), 80)
            self.assertEqual(self.number_value("sensor.mock_charger_power_w"), 0)
            self.assertEqual(self.number_value("sensor.mock_battery_soc"), 0)
            self.assertEqual(self.number_value("sensor.mock_battery_power"), 0)
            self.assertEqual(
                self.number_value("sensor.mock_battery_power_charge_positive_w"), 0
            )
            self.assertEqual(self.number_value("sensor.mock_grid_power"), 12)
            self.assertEqual(
                self.hass.states.get("sensor.mock_charger_state").state, "charger_end"
            )
            await self.command("button", "press", "button.mock_reset_simulator")
            cancel.assert_called_once()
            self.assertEqual(self.number_value("sensor.mock_ev_battery_soc"), 50)
            self.assertEqual(self.number_value("sensor.mock_battery_soc"), 65)
            self.assertEqual(self.number_value("number.mock_simulation_speed"), 1)
            self.assertEqual(
                self.hass.states.get("switch.mock_dynamic_enabled").state, "off"
            )
            clock.return_value = 1000
            tick(datetime.now(UTC))
            await self.hass.async_block_till_done()
            self.assertEqual(self.number_value("sensor.mock_grid_power"), 0)
            cancel.reset_mock()
            await self.command("switch", "turn_on", "switch.mock_dynamic_enabled")
            coordinator = entry.runtime_data
            self.assertTrue(await self.hass.config_entries.async_unload(entry.entry_id))
            cancel.assert_called_once()
            snapshot = coordinator.data
            clock.return_value = 2000
            tick(datetime.now(UTC))
            self.assertEqual(coordinator.data, snapshot)

    async def test_real_home_assistant_timer_advances_soc(self) -> None:
        """A real scheduled HA interval publishes SOC changes without manual ticks."""
        with patch(
            "custom_components.mock_solar.coordinator.monotonic", return_value=0
        ) as clock:
            entry = await self.create_simulator()
            await self.command(
                "number",
                "set_value",
                "number.mock_charger_session_current_limit",
                value=16,
            )
            await self.command(
                "switch", "turn_on", "switch.mock_charger_charge_control"
            )
            advanced = asyncio.Event()
            initial_soc = self.number_value("sensor.mock_ev_battery_soc")

            @callback
            def observe(event: Event) -> None:
                if event.data["entity_id"] == "sensor.mock_ev_battery_soc":
                    state = event.data["new_state"]
                    if (
                        state is not None
                        and state.state not in {"unknown", "unavailable"}
                        and float(state.state) > initial_soc
                    ):
                        advanced.set()

            unsubscribe = self.hass.bus.async_listen("state_changed", observe)
            try:
                await self.command("switch", "turn_on", "switch.mock_dynamic_enabled")
                clock.return_value = 60
                await asyncio.wait_for(advanced.wait(), timeout=5)
                self.assertAlmostEqual(
                    self.number_value("sensor.mock_ev_battery_soc"), 50.076
                )
                self.assertTrue(
                    await self.hass.config_entries.async_unload(entry.entry_id)
                )
            finally:
                unsubscribe()
