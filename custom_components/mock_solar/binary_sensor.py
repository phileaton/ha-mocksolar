"""Read-only vehicle connection telemetry."""

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .entity import MockSolarEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import MockSolarConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 HA platform interface
    entry: MockSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose vehicle connection independently from the charging control."""
    async_add_entities(
        [MockSolarConnected(entry.runtime_data, "ev_connected", "EV connection")]
    )


class MockSolarConnected(MockSolarEntity, BinarySensorEntity):
    """Vehicle cable connection, not cloud or hardware availability."""

    entity_id = "binary_sensor.mock_ev_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool:
        """Return whether the simulated vehicle is connected."""
        return self.coordinator.data.charger_connected
