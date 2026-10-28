"""Native charger lifecycle and grid override controls."""

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity

from .entity import MockSolarEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MockSolarCoordinator
    from .data import MockSolarConfigEntry

SWITCHES = (
    ("dynamic_enabled", "Dynamic simulation", "dynamic_enabled"),
    ("charger_charge_control", "Charger charge control", "charger_enabled"),
    ("charger_connected", "EV connected", "charger_connected"),
    ("charger_force_finishing", "Force charging finished", "charger_force_finishing"),
    ("grid_override_enabled", "Grid override enabled", "grid_override_enabled"),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 HA platform interface
    entry: MockSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up standard switches for local simulation controls."""
    async_add_entities(MockSolarSwitch(entry.runtime_data, *item) for item in SWITCHES)


class MockSolarSwitch(MockSolarEntity, SwitchEntity):
    """One boolean input; enabling charging need not imply power flow."""

    def __init__(
        self,
        coordinator: MockSolarCoordinator,
        key: str,
        name: str,
        attribute: str,
    ) -> None:
        """Describe the model boolean controlled by this switch."""
        super().__init__(coordinator, key, name)
        self.entity_id = f"switch.mock_{key}"
        self._attribute = attribute

    @property
    def is_on(self) -> bool:
        """Return the actual control state."""
        return getattr(self.coordinator.data, self._attribute)

    async def async_turn_on(self, **_: Any) -> None:
        """Enable this input and immediately recalculate outputs."""
        self.coordinator.set_input(self._attribute, value=True)

    async def async_turn_off(self, **_: Any) -> None:
        """Disable this input and immediately recalculate outputs."""
        self.coordinator.set_input(self._attribute, value=False)
