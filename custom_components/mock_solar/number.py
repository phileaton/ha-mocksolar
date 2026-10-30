"""Native manual inputs and externally controllable charger current limits."""

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.exceptions import HomeAssistantError

from .entity import MockSolarEntity
from .simulation import NUMBER_LIMITS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MockSolarCoordinator
    from .data import MockSolarConfigEntry

# Preserve the two public charger number IDs; other controls replace helpers.
NUMBERS = (
    ("solar_kw", "Solar production", "solar_kw", UnitOfPower.KILO_WATT),
    ("house_kw", "Home load (excl. EV)", "house_kw", UnitOfPower.KILO_WATT),
    ("battery_soc_setting", "Battery SOC setting", "battery_soc_setting", PERCENTAGE),
    (
        "charger_maximum_current",
        "Charger maximum current",
        "charger_max_amps_setting",
        UnitOfElectricCurrent.AMPERE,
    ),
    (
        "charger_session_current_limit",
        "Charger session current limit",
        "charger_session_amps_setting",
        UnitOfElectricCurrent.AMPERE,
    ),
    ("ev_soc_setting", "EV SOC setting", "ev_soc_setting", PERCENTAGE),
    (
        "battery_capacity_kwh",
        "Home battery capacity",
        "battery_capacity_kwh",
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    (
        "ev_capacity_kwh",
        "EV battery capacity",
        "ev_capacity_kwh",
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    (
        "ev_charging_efficiency",
        "EV charging efficiency",
        "ev_charging_efficiency",
        PERCENTAGE,
    ),
    ("ev_target_soc", "EV target SOC", "ev_target_soc", PERCENTAGE),
    (
        "forecast_daily_kwh",
        "Solar forecast today",
        "forecast_daily_kwh",
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    (
        "forecast_remaining_percent",
        "Solar forecast remaining override",
        "forecast_remaining_percent",
        PERCENTAGE,
    ),
    ("simulation_speed", "Simulation speed multiplier", "simulation_speed", None),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 HA platform interface
    entry: MockSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the simulator controls."""
    async_add_entities(MockSolarNumber(entry.runtime_data, *item) for item in NUMBERS)


class MockSolarNumber(MockSolarEntity, NumberEntity):
    """A validated manual input shared by every output."""

    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: MockSolarCoordinator,
        key: str,
        name: str,
        attribute: str,
        unit: str | None,
    ) -> None:
        """Initialize bounds and units from the model contract."""
        super().__init__(coordinator, key, name)
        self.entity_id = f"number.mock_{key}"
        self._attribute = attribute
        minimum, maximum, step = NUMBER_LIMITS[attribute]
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float:
        """Return the current control value."""
        return getattr(self.coordinator.data, self._attribute)

    async def async_set_native_value(self, value: float) -> None:
        """Apply an external command without polling or network IO."""
        try:
            self.coordinator.set_input(self._attribute, value=value)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
