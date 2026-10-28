"""Verify manual energy balance and reproducible charger scenarios."""

import unittest
from dataclasses import FrozenInstanceError, replace

from custom_components.mock_solar.simulation import SimulationState


class SimulationTests(unittest.TestCase):
    """Exercise physics and lifecycle behavior independently of HA entities."""

    def test_defaults_and_discharge_sign(self) -> None:
        """Surplus charges the battery (negative) and a deficit discharges it."""
        state = SimulationState()
        self.assertEqual(state.charger_power, 0)
        self.assertEqual(state.home_load, 2)
        self.assertEqual(state.battery_power, -6)
        self.assertEqual(state.grid_power, 0)
        self.assertEqual(replace(state, solar_kw=0).battery_power, 2)
        self.assertEqual(replace(state, solar_kw=0).grid_power, 0)

    def test_handoff_energy_balance(self) -> None:
        """Eight kW solar and six kW load charges the battery by two."""
        state = SimulationState(
            charger_enabled=True,
            charger_max_amps_setting=40,
            charger_session_amps_setting=4000 / 240,
        )
        self.assertEqual(state.charger_power, 4)
        self.assertEqual(state.home_load, 6)
        self.assertEqual(state.battery_power, -2)
        self.assertEqual(state.grid_power, 0)

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

    def test_battery_limits_and_grid_remainder(self) -> None:
        """Battery is capped; empty or full batteries leave the rest to the grid."""
        big = SimulationState(solar_kw=20, house_kw=0)
        self.assertEqual(big.battery_power, -12)
        self.assertEqual(big.grid_power, -8)
        full = replace(SimulationState(), battery_soc_setting=100)
        self.assertEqual(full.battery_power, 0)
        self.assertEqual(full.grid_power, -6)
        empty = replace(SimulationState(solar_kw=0), battery_soc_setting=0)
        self.assertEqual(empty.battery_power, 0)
        self.assertEqual(empty.grid_power, 2)

    def test_bounds_and_nonfinite_values(self) -> None:
        """Invalid inputs cannot contaminate shared state or produce NaN output."""
        for key, value in (
            ("solar_kw", -1),
            ("house_kw", 21),
                        ("battery_soc_setting", 101),
            ("ev_soc_setting", -1),
            ("charger_max_amps_setting", 0),
            ("charger_session_amps_setting", 41),
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
        self.assertEqual(updated.grid_power, 0)
        self.assertEqual(updated.battery_power, -8)
        with self.assertRaises(FrozenInstanceError):
            state.solar_kw = 0
