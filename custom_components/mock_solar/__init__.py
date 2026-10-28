"""Set up the hardware-independent Mock Solar simulator."""

from typing import TYPE_CHECKING

from homeassistant.const import Platform

from .const import CONFIG_VERSION
from .coordinator import MockSolarCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import MockSolarConfigEntry

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MockSolarConfigEntry) -> bool:
    """Set up a manual simulator without cloud credentials."""
    entry.runtime_data = MockSolarCoordinator(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


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
