"""Pure, immutable manual energy model, with powers expressed in kW."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

MIN_CHARGING_CURRENT = 6

# Minimum, maximum and step; shared by validation and native number entities.
NUMBER_LIMITS = {
    "solar_kw": (0, 20, 0.1),
    "house_kw": (0, 20, 0.1),
    "battery_kw": (-12, 12, 0.1),
    "battery_soc_setting": (0, 100, 1),
    "grid_override_kw": (-20, 20, 0.1),
    "charger_max_amps_setting": (6, 40, 1),
    "charger_session_amps_setting": (0, 40, 1),
    "ev_soc_setting": (0, 100, 1),
}
SWITCH_KEYS = (
    "grid_override_enabled",
    "charger_connected",
    "charger_enabled",
    "charger_force_finishing",
)


@dataclass(frozen=True)
class SimulationState:
    """Manual inputs and consistent derived telemetry; no timers or hardware IO."""

    solar_kw: float = 8
    house_kw: float = 2
    battery_kw: float = -2
    battery_soc_setting: float = 65
    grid_override_kw: float = 0
    charger_max_amps_setting: float = 16
    charger_session_amps_setting: float = 0
    ev_soc_setting: float = 50
    grid_override_enabled: bool = False
    charger_connected: bool = True
    charger_enabled: bool = False
    charger_force_finishing: bool = False

    def __post_init__(self) -> None:
        """Reject invalid values before they enter shared state."""
        for key, (minimum, maximum, _) in NUMBER_LIMITS.items():
            value = getattr(self, key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or not minimum <= value <= maximum
            ):
                msg = f"{key} must be finite and between {minimum} and {maximum}"
                raise ValueError(msg)
        for key in SWITCH_KEYS:
            if not isinstance(getattr(self, key), bool):
                msg = f"{key} must be a boolean"
                raise TypeError(msg)

    def with_input(self, key: str, *, value: float | bool) -> SimulationState:
        """Return a validated replacement without mutating the current snapshot."""
        if key not in NUMBER_LIMITS and key not in SWITCH_KEYS:
            msg = f"Unknown simulation input: {key}"
            raise ValueError(msg)
        return replace(self, **{key: value})

    @property
    def charger_current(self) -> float:
        """Return permitted active current; subminimum settings suspend charging."""
        permitted = min(
            self.charger_max_amps_setting, self.charger_session_amps_setting
        )
        if (
            not self.charger_connected
            or not self.charger_enabled
            or self.charger_force_finishing
            or permitted < MIN_CHARGING_CURRENT
        ):
            return 0
        return permitted

    @property
    def charger_power(self) -> float:
        """Return single-phase EV consumption at the prototype's 240 V."""
        return round(240 * self.charger_current / 1000, 3)

    @property
    def home_load(self) -> float:
        """Return total household load, including EV consumption."""
        return round(self.house_kw + self.charger_power, 3)

    @property
    def calculated_grid_power(self) -> float:
        """Return balanced grid exchange, positive import, negative export."""
        return round(self.home_load - self.solar_kw - self.battery_kw, 3)

    @property
    def grid_power(self) -> float:
        """Return effective grid reading, leaving manual battery power unchanged."""
        if self.grid_override_enabled:
            return self.grid_override_kw
        return self.calculated_grid_power

    @property
    def charger_state(self) -> str:
        """Return normalized lifecycle status, with disconnection taking priority."""
        if not self.charger_connected:
            return "charger_free"
        if self.charger_force_finishing:
            return "charger_end"
        if self.charger_power > 0:
            return "charger_charging"
        return "charger_wait"

    @property
    def charger_status_connector(self) -> str:
        """Preserve the prototype's OCPP-style vocabulary."""
        states = {
            "charger_free": "Available",
            "charger_end": "Finishing",
            "charger_charging": "Charging",
        }
        if self.charger_state in states:
            return states[self.charger_state]
        return "SuspendedEVSE" if self.charger_enabled else "Preparing"
