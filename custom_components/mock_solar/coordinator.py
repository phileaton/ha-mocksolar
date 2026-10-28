"""Publish atomic local simulation snapshots to all entities."""

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER
from .simulation import SimulationState

if TYPE_CHECKING:
    from .data import MockSolarConfigEntry


class MockSolarCoordinator(DataUpdateCoordinator[SimulationState]):
    """Event-driven coordinator; no network polling or background timers."""

    def __init__(self, hass: HomeAssistant, entry: MockSolarConfigEntry) -> None:
        """Initialize the simulator with repeatable prototype defaults."""
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry)
        self.async_set_updated_data(SimulationState())

    @callback
    def set_input(self, key: str, *, value: float | bool) -> None:
        """Validate one command and immediately notify every entity."""
        self.async_set_updated_data(self.data.with_input(key, value=value))

    async def _async_update_data(self) -> SimulationState:
        """Return local state for explicit Home Assistant refresh requests."""
        return self.data
