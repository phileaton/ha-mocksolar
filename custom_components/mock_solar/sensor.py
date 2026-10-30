"""Read-only derived energy telemetry."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .entity import MockSolarEntity
from .simulation import SimulationState

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MockSolarCoordinator
    from .data import MockSolarConfigEntry

# Entity key, display name, model attribute, device class, unit.
SENSORS = (
    (
        "solar_power",
        "Solar power",
        "solar_kw",
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
    ),
    (
        "home_load",
        "Home load (incl. EV)",
        "home_load",
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
    ),
    (
        "battery_soc",
        "Battery SOC",
        "battery_soc_setting",
        SensorDeviceClass.BATTERY,
        PERCENTAGE,
    ),
    (
        "battery_power",
        "Battery power",
        "battery_power",
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
    ),
    (
        "grid_power",
        "Grid power",
        "grid_power",
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
    ),
    (
        "charger_power",
        "Charger power",
        "charger_power",
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
    ),
    (
        "ev_battery_soc",
        "EV battery SOC",
        "ev_soc_setting",
        SensorDeviceClass.BATTERY,
        PERCENTAGE,
    ),
    ("charger_state", "Charger state", "charger_state", None, None),
    (
        "charger_status_connector",
        "Charger status connector",
        "charger_status_connector",
        None,
        None,
    ),
)


# Explicit adapters retain the original kW outputs and discharge-positive sign.
# Entity key, display name, model attribute, kW-to-W conversion factor.
COMPATIBILITY_SENSORS = (
    ("solar_power_w", "Solar power W", "solar_kw", 1000),
    ("house_load_w", "Home load (excl. EV) W", "house_kw", 1000),
    ("home_load_w", "Home load W", "home_load", 1000),
    ("grid_power_w", "Grid power W", "grid_power", 1000),
    ("charger_power_w", "Charger power W", "charger_power", 1000),
    (
        "battery_power_charge_positive_w",
        "Battery power W (positive charging)",
        "battery_power",
        -1000,
    ),
)

FORECAST_REFRESH = timedelta(minutes=1)

# Entity key, display name, function(state, local hour), device class, unit.
FORECAST_SENSORS = (
    (
        "forecast_energy_today",
        "Solar forecast energy today",
        lambda state, _hour: state.forecast_daily_kwh,
        SensorDeviceClass.ENERGY,
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    (
        "forecast_energy_produced_today",
        "Solar forecast energy produced so far today",
        lambda state, hour: (
            state.forecast_daily_kwh - state.forecast_remaining_kwh(hour)
        ),
        SensorDeviceClass.ENERGY,
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    (
        "forecast_energy_remaining_today",
        "Solar forecast energy remaining today",
        SimulationState.forecast_remaining_kwh,
        SensorDeviceClass.ENERGY,
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    (
        "forecast_power_now",
        "Solar forecast power now",
        SimulationState.forecast_power_kw,
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 HA platform interface
    entry: MockSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose a consistent snapshot through standard sensors."""
    async_add_entities(
        [MockSolarSensor(entry.runtime_data, *item) for item in SENSORS]
        + [
            MockSolarSensor(
                entry.runtime_data,
                key,
                name,
                attribute,
                SensorDeviceClass.POWER,
                UnitOfPower.WATT,
                scale=scale,
            )
            for key, name, attribute, scale in COMPATIBILITY_SENSORS
        ]
        + [
            MockSolarForecastSensor(entry.runtime_data, *item)
            for item in FORECAST_SENSORS
        ]
    )


class MockSolarForecastSensor(MockSolarEntity, SensorEntity):
    """Forecast.Solar-style estimate derived from the daily forecast slider."""

    def __init__(  # noqa: PLR0913 Sensor metadata fields
        self,
        coordinator: MockSolarCoordinator,
        key: str,
        name: str,
        calculate: Callable[[SimulationState, float], float],
        device_class: SensorDeviceClass,
        unit: str,
    ) -> None:
        """Describe the forecast calculation and its metadata."""
        super().__init__(coordinator, key, name)
        self.entity_id = f"sensor.mock_{key}"
        self._calculate = calculate
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

    async def async_added_to_hass(self) -> None:
        """Refresh periodically because the forecast follows the wall clock."""
        await super().async_added_to_hass()

        @callback
        def _refresh(_now: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_time_interval(self.hass, _refresh, FORECAST_REFRESH)
        )

    @property
    def native_value(self) -> float:
        """Return the forecast for the current local time."""
        now = dt_util.now()
        hour = now.hour + now.minute / 60 + now.second / 3600
        return round(self._calculate(self.coordinator.data, hour), 3)


class MockSolarSensor(MockSolarEntity, SensorEntity):
    """One numeric or textual simulation output."""

    def __init__(  # noqa: PLR0913 Sensor metadata fields
        self,
        coordinator: MockSolarCoordinator,
        key: str,
        name: str,
        attribute: str,
        device_class: SensorDeviceClass | None,
        unit: str | None,
        *,
        scale: float = 1,
    ) -> None:
        """Describe the model attribute and its metadata."""
        super().__init__(coordinator, key, name)
        self.entity_id = f"sensor.mock_{key}"
        self._attribute = attribute
        self._scale = scale
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        if unit is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key == "charger_state":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = [
                "charger_free",
                "charger_wait",
                "charger_charging",
                "charger_end",
            ]

    @property
    def native_value(self) -> float | str:
        """Return the current model output."""
        value = getattr(self.coordinator.data, self._attribute)
        if isinstance(value, str):
            return value
        return round(value * self._scale, 3)

    @property
    def extra_state_attributes(self) -> dict[str, bool | float | str] | None:
        """Describe the sign convention of the charge-positive adapter."""
        if self._key == "battery_power_charge_positive_w":
            return {"positive_direction": "charging"}
        return None
