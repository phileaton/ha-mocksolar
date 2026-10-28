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
        "battery_kw",
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


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 HA platform interface
    entry: MockSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose a consistent snapshot through standard sensors."""
    async_add_entities(MockSolarSensor(entry.runtime_data, *item) for item in SENSORS)


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
    ) -> None:
        """Describe the model attribute and its metadata."""
        super().__init__(coordinator, key, name)
        self.entity_id = f"sensor.mock_{key}"
        self._attribute = attribute
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
        return getattr(self.coordinator.data, self._attribute)

    @property
    def extra_state_attributes(self) -> dict[str, bool | float] | None:
        """Make forced grid readings identifiable alongside the calculated value."""
        if self._key == "grid_power":
            return {
                "override_enabled": self.coordinator.data.grid_override_enabled,
                "calculated_power_kw": self.coordinator.data.calculated_grid_power,
            }
        return None
