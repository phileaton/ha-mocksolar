"""Publish atomic local simulation snapshots and advance optional dynamic time."""

from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LOGGER
from .simulation import SimulationState

if TYPE_CHECKING:
    from collections.abc import Callable

    from .dashboard import MockSolarDashboard
    from .data import MockSolarConfigEntry

TICK_INTERVAL = timedelta(seconds=1)


class MockSolarCoordinator(DataUpdateCoordinator[SimulationState]):
    """Advance monotonic elapsed time, settling old inputs before each command."""

    dashboard: MockSolarDashboard

    def __init__(self, hass: HomeAssistant, entry: MockSolarConfigEntry) -> None:
        """Initialize repeatable defaults with dynamic mode disabled."""
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry)
        self._last_tick = monotonic()
        self._cancel_tick: Callable[[], None] | None = None
        self._closed = False
        self.async_set_updated_data(SimulationState())

    def _advance_to(self, now: float) -> SimulationState:
        """Settle elapsed time under the previous inputs, then move the clock."""
        state = self.data.advance(max(0, now - self._last_tick))
        self._last_tick = now
        return state

    @callback
    def set_input(self, key: str, *, value: float | bool) -> None:
        """Validate a command and integrate the prior interval before applying it."""
        self.data.with_input(key, value=value)
        state = self._advance_to(monotonic()).with_input(key, value=value)
        self.async_set_updated_data(state)
        self._sync_timer()

    @callback
    def reset(self) -> None:
        """Restore defaults, stop the clock and keep existing entity identities."""
        self._last_tick = monotonic()
        self.async_set_updated_data(SimulationState())
        self._sync_timer()

    @callback
    def _sync_timer(self) -> None:
        """Keep exactly one timer while dynamic simulation is enabled."""
        if self.data.dynamic_enabled and not self._closed:
            if self._cancel_tick is None:
                self._cancel_tick = async_track_time_interval(
                    self.hass, self._tick, TICK_INTERVAL
                )
        elif self._cancel_tick is not None:
            self._cancel_tick()
            self._cancel_tick = None

    @callback
    def _tick(self, _now: datetime) -> None:
        """Use elapsed monotonic time rather than assuming a punctual timer."""
        if self._closed or not self.data.dynamic_enabled:
            return
        self.async_set_updated_data(self._advance_to(monotonic()))

    async def _async_update_data(self) -> SimulationState:
        """Settle local state for explicit Home Assistant refresh requests."""
        return self._advance_to(monotonic())

    async def async_shutdown(self) -> None:
        """Cancel the simulation timer on entry unload or Home Assistant stop."""
        self._closed = True
        self._sync_timer()
        await super().async_shutdown()
