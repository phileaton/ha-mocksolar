"""Reset the simulator to a repeatable initial scenario."""

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

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
    """Create a reset control without recreating any entities."""
    async_add_entities(
        [
            MockSolarReset(entry.runtime_data, "reset_simulator", "Reset simulator"),
            MockSolarRegenerate(
                entry.runtime_data, "regenerate_dashboard", "Regenerate dashboard"
            ),
        ]
    )


class MockSolarReset(MockSolarEntity, ButtonEntity):
    """Restore input defaults and return to manual mode."""

    entity_id = "button.mock_reset_simulator"
    _attr_icon = "mdi:restart"

    async def async_press(self) -> None:
        """Reset the shared model and stop any active simulation timer."""
        self.coordinator.reset()


class MockSolarRegenerate(MockSolarEntity, ButtonEntity):
    """Explicitly replace the generated dashboard layout on user request."""

    entity_id = "button.mock_regenerate_dashboard"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:view-dashboard-edit"

    async def async_press(self) -> None:
        """Rebuild the dashboard with current registry IDs and the bundled layout."""
        await self.coordinator.dashboard.async_ensure(regenerate=True)
