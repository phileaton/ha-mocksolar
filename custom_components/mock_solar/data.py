"""Config entry type for the local simulator."""

from homeassistant.config_entries import ConfigEntry

from .coordinator import MockSolarCoordinator

type MockSolarConfigEntry = ConfigEntry[MockSolarCoordinator]
