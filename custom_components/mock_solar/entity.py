"""Shared device identity and stable entity IDs for Mock Solar."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MockSolarCoordinator


class MockSolarEntity(CoordinatorEntity[MockSolarCoordinator]):
    """Represent one value of the shared simulator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MockSolarCoordinator, key: str, name: str) -> None:
        """Initialize stable per-entry identity and suggested legacy object ID."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="Mock Solar",
            manufacturer="Mock Solar",
            model="Energy simulator",
        )
