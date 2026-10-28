"""Read-only derived energy telemetry."""

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfPower

from .entity import MockSolarEntity

if TYPE_CHECKING:
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
        "home_base_load",
        "Base home load",
        "house_kw",
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
    ),
    (
        "home_load",
        "Home load",
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
        "calculated_grid_power",
        "Calculated grid power",
        "calculated_grid_power",
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
    ("home_base_load_w", "Base home load W", "house_kw", 1000),
    ("home_load_w", "Home load W", "home_load", 1000),
    ("grid_power_w", "Grid power W", "grid_power", 1000),
    (
        "calculated_grid_power_w",
        "Calculated grid power W",
        "calculated_grid_power",
        1000,
    ),
    ("charger_power_w", "Charger power W", "charger_power", 1000),
    (
        "battery_power_charge_positive_w",
        "Battery power W (positive charging)",
        "battery_power",
        -1000,
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
    )


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
        """Make forced grid readings identifiable alongside the calculated value."""
        if self._key in {"grid_power", "grid_power_w"}:
            return {
                "override_enabled": self.coordinator.data.grid_override_enabled,
                "calculated_power_kw": self.coordinator.data.calculated_grid_power,
            }
        if self._key == "battery_power_charge_positive_w":
            return {"positive_direction": "charging"}
        return None
