"""Verify manual energy balance and reproducible charger scenarios."""

import unittest
from dataclasses import FrozenInstanceError, replace

from custom_components.mock_solar.simulation import SimulationState


class SimulationTests(unittest.TestCase):
    """Exercise physics and lifecycle behavior independently of HA entities."""

    def test_defaults_and_discharge_sign(self) -> None:
        """Default charging battery increases grid import relative to idle."""
        state = SimulationState()
        self.assertEqual(state.charger_power, 0)
        self.assertEqual(state.home_load, 2)
        self.assertEqual(state.grid_power, -4)
        self.assertEqual(replace(state, battery_kw=2).grid_power, -8)
        self.assertEqual(replace(state, solar_kw=0).grid_power, 4)

    def test_handoff_energy_balance(self) -> None:
        """Eight kW solar and six kW load with one kW battery charge exports one."""
        state = SimulationState(
            battery_kw=-1,
            charger_enabled=True,
            charger_max_amps_setting=40,
            charger_session_amps_setting=4000 / 240,
        )
        self.assertEqual(state.charger_power, 4)
        self.assertEqual(state.home_load, 6)
        self.assertEqual(state.grid_power, -1)

    def test_both_current_limits(self) -> None:
        """Either current setting can constrain the EV independently."""
        state = SimulationState(charger_enabled=True, charger_session_amps_setting=40)
        self.assertEqual(state.charger_current, 16)
        self.assertEqual(state.charger_power, 3.84)
        self.assertEqual(
            replace(state, charger_session_amps_setting=6).charger_power, 1.44
        )
        self.assertEqual(replace(state, charger_max_amps_setting=40).charger_power, 9.6)

    def test_subminimum_current_suspends(self) -> None:
        """Zero through five amps never produces power, even while enabled."""
        for current in range(6):
            with self.subTest(current=current):
                state = SimulationState(
                    charger_enabled=True, charger_session_amps_setting=current
                )
                self.assertEqual(state.charger_power, 0)
                self.assertEqual(state.charger_state, "charger_wait")
                self.assertEqual(state.charger_status_connector, "SuspendedEVSE")

    def test_lifecycle_and_priority(self) -> None:
        """Connection overrides finished; disabled and finished both stop draw."""
        charging = SimulationState(
            charger_enabled=True, charger_session_amps_setting=16
        )
        cases = (
            (charging, "charger_charging", "Charging", 3.84),
            (replace(charging, charger_enabled=False), "charger_wait", "Preparing", 0),
            (
                replace(charging, charger_force_finishing=True),
                "charger_end",
                "Finishing",
                0,
            ),
            (
                replace(
                    charging, charger_connected=False, charger_force_finishing=True
                ),
                "charger_free",
                "Available",
                0,
            ),
        )
        for state, normalized, connector, power in cases:
            with self.subTest(status=normalized):
                self.assertEqual(state.charger_state, normalized)
                self.assertEqual(state.charger_status_connector, connector)
                self.assertEqual(state.charger_power, power)

    def test_override_keeps_battery_and_calculated_grid(self) -> None:
        """A deliberately forced reading does not silently balance the battery."""
        state = SimulationState(grid_override_enabled=True, grid_override_kw=7)
        self.assertEqual(state.grid_power, 7)
        self.assertEqual(state.calculated_grid_power, -4)
        self.assertEqual(state.battery_kw, -2)
        self.assertEqual(replace(state, grid_override_enabled=False).grid_power, -4)

    def test_bounds_and_nonfinite_values(self) -> None:
        """Invalid inputs cannot contaminate shared state or produce NaN output."""
        for key, value in (
            ("solar_kw", -1),
            ("house_kw", 21),
            ("battery_kw", 13),
            ("battery_soc_setting", 101),
            ("ev_soc_setting", -1),
            ("charger_max_amps_setting", 0),
            ("charger_session_amps_setting", 41),
            ("grid_override_kw", float("inf")),
            ("solar_kw", float("nan")),
            ("house_kw", True),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                SimulationState().with_input(key, value=value)
        with self.assertRaises(TypeError):
            SimulationState().with_input("charger_enabled", value=1)
        with self.assertRaises(ValueError):
            SimulationState().with_input("unknown", value=1)

    def test_snapshot_is_immutable(self) -> None:
        """Commands leave old snapshots intact and validate the new snapshot."""
        state = SimulationState()
        updated = state.with_input("solar_kw", value=10)
        self.assertEqual(state.solar_kw, 8)
        self.assertEqual(updated.grid_power, -6)
        with self.assertRaises(FrozenInstanceError):
            state.solar_kw = 0
