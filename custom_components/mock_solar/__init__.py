"""Set up the hardware-independent Mock Solar simulator."""

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError

from .const import CONFIG_VERSION, LOGGER
from .coordinator import MockSolarCoordinator
from .dashboard import MockSolarDashboard

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import MockSolarConfigEntry

PLATFORMS = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: MockSolarConfigEntry) -> bool:
    """Set up a local simulator, starting in manual mode."""
    entry.runtime_data = MockSolarCoordinator(hass, entry)
    entry.runtime_data.dashboard = MockSolarDashboard(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    await async_update_options(hass, entry)
    return True


async def async_update_options(
    hass: HomeAssistant,  # noqa: ARG001 HA update-listener interface
    entry: MockSolarConfigEntry,
) -> None:
    """Apply optional dashboard creation without resetting the simulator."""
    try:
        await entry.runtime_data.dashboard.async_ensure()
    except HomeAssistantError, OSError, ValueError:
        LOGGER.exception(
            "Unable to create Energy Lab dashboard; simulator remains available"
        )


async def async_unload_entry(hass: HomeAssistant, entry: MockSolarConfigEntry) -> bool:
    """Unload platforms and their coordinator subscriptions."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: MockSolarConfigEntry) -> bool:
    """Discard obsolete blueprint credentials when upgrading a sample entry."""
    if entry.version > CONFIG_VERSION:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry, data={}, version=CONFIG_VERSION, title="Mock Solar"
        )
    return True
