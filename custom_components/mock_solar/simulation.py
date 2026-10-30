"""Pure, immutable manual and elapsed-time energy model, with powers expressed in kW."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import cos, isfinite, pi, sin

MIN_CHARGING_CURRENT = 6
MAX_SOC = 100
BATTERY_MAX_KW = 12
SUNRISE_HOUR = 6
SUNSET_HOUR = 18

# Minimum, maximum and step; shared by validation and native number entities.
NUMBER_LIMITS = {
    "solar_kw": (0, 20, 0.1),
    "house_kw": (0, 20, 0.1),
    "battery_soc_setting": (0, 100, 1),
    "charger_max_amps_setting": (6, 40, 1),
    "charger_session_amps_setting": (0, 40, 1),
    "ev_soc_setting": (0, 100, 1),
    "battery_capacity_kwh": (1, 100, 0.1),
    "ev_capacity_kwh": (1, 200, 1),
    "ev_charging_efficiency": (1, 100, 1),
    "ev_target_soc": (0, 100, 1),
    "simulation_speed": (1, 3600, 1),
    "forecast_daily_kwh": (0, 200, 0.5),
    "forecast_remaining_percent": (0, 100, 1),
}
SWITCH_KEYS = (
    "dynamic_enabled",
    "charger_connected",
    "charger_enabled",
    "charger_force_finishing",
    "forecast_override_enabled",
)


@dataclass(frozen=True)
class SimulationState:
    """Manual inputs and consistent derived telemetry; no timers or hardware IO."""

    solar_kw: float = 8
    house_kw: float = 2
    battery_soc_setting: float = 65
    charger_max_amps_setting: float = 16
    charger_session_amps_setting: float = 0
    ev_soc_setting: float = 50
    battery_capacity_kwh: float = 13.5
    ev_capacity_kwh: float = 80
    ev_charging_efficiency: float = 95
    ev_target_soc: float = 80
    simulation_speed: float = 1
    forecast_daily_kwh: float = 30
    forecast_remaining_percent: float = 100
    dynamic_enabled: bool = False
    charger_connected: bool = True
    charger_enabled: bool = False
    charger_force_finishing: bool = False
    forecast_override_enabled: bool = False

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

    def advance(self, elapsed_seconds: float) -> SimulationState:
        """Advance real elapsed seconds, scaling time and limiting stored energy."""
        if (
            isinstance(elapsed_seconds, bool)
            or not isinstance(elapsed_seconds, (int, float))
            or not isfinite(elapsed_seconds)
            or elapsed_seconds < 0
        ):
            msg = "Elapsed seconds must be finite and nonnegative"
            raise ValueError(msg)
        if not self.dynamic_enabled or elapsed_seconds == 0:
            return self
        hours = elapsed_seconds / 3600 * self.simulation_speed
        battery_soc = min(
            100,
            max(
                0,
                self.battery_soc_setting
                - self.battery_power * hours / self.battery_capacity_kwh * 100,
            ),
        )
        ev_soc = self.ev_soc_setting
        if self.charger_power > 0:
            ev_soc = min(
                self.ev_target_soc,
                ev_soc
                + self.charger_power
                * hours
                * (self.ev_charging_efficiency / 100)
                / self.ev_capacity_kwh
                * 100,
            )
        return replace(self, battery_soc_setting=battery_soc, ev_soc_setting=ev_soc)

    def forecast_remaining_kwh(self, hour: float) -> float:
        """Return remaining forecast energy, from the slider when overridden."""
        if self.forecast_override_enabled:
            return self.forecast_daily_kwh * self.forecast_remaining_percent / 100
        return forecast_energy_remaining_kwh(self.forecast_daily_kwh, hour)

    def forecast_power_kw(self, hour: float) -> float:
        """Return forecast power, zero once an override leaves nothing to produce."""
        if self.forecast_override_enabled and self.forecast_remaining_percent == 0:
            return 0
        return forecast_power_kw(self.forecast_daily_kwh, hour)

    @property
    def battery_power(self) -> float:
        """Return battery flow (positive discharging) that covers the net load."""
        needed = self.home_load - self.solar_kw
        if (self.battery_soc_setting <= 0 and needed > 0) or (
            self.battery_soc_setting >= MAX_SOC and needed < 0
        ):
            return 0
        return round(max(-BATTERY_MAX_KW, min(BATTERY_MAX_KW, needed)), 3)

    @property
    def charging_finished(self) -> bool:
        """Combine explicit finish control with dynamic target completion."""
        return self.charger_force_finishing or (
            self.dynamic_enabled and self.ev_soc_setting >= self.ev_target_soc
        )

    @property
    def charger_current(self) -> float:
        """Return permitted active current; subminimum settings suspend charging."""
        permitted = min(
            self.charger_max_amps_setting, self.charger_session_amps_setting
        )
        if (
            not self.charger_connected
            or not self.charger_enabled
            or self.charging_finished
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
    def grid_power(self) -> float:
        """Return grid exchange after solar and battery, positive import."""
        return round(self.home_load - self.solar_kw - self.battery_power, 3)

    @property
    def charger_state(self) -> str:
        """Return normalized lifecycle status, with disconnection taking priority."""
        if not self.charger_connected:
            return "charger_free"
        if self.charging_finished:
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


def _daylight_fraction(hour: float) -> float:
    """Return the share (0-1) of daily energy produced by a local hour."""
    progress = (hour - SUNRISE_HOUR) / (SUNSET_HOUR - SUNRISE_HOUR)
    progress = min(1, max(0, progress))
    return (1 - cos(pi * progress)) / 2


def forecast_energy_so_far_kwh(daily_kwh: float, hour: float) -> float:
    """Return forecast energy produced today up to a local hour (half-sine day)."""
    return daily_kwh * _daylight_fraction(hour)


def forecast_energy_remaining_kwh(daily_kwh: float, hour: float) -> float:
    """Return forecast energy still to be produced today."""
    return daily_kwh - forecast_energy_so_far_kwh(daily_kwh, hour)


def forecast_power_kw(daily_kwh: float, hour: float) -> float:
    """Return forecast power at a local hour, peaking at solar noon."""
    if not SUNRISE_HOUR < hour < SUNSET_HOUR:
        return 0
    duration = SUNSET_HOUR - SUNRISE_HOUR
    progress = (hour - SUNRISE_HOUR) / duration
    return daily_kwh * pi / (2 * duration) * sin(pi * progress)
