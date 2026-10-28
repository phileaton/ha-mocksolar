"""Create editable Lovelace dashboards without replacing user edits on reload."""

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components import frontend, websocket_api
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import (
    DashboardsCollection,
    DashboardsCollectionWebSocket,
    LovelaceStorage,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from .const import CONF_CREATE_DASHBOARD, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import MockSolarConfigEntry

DASHBOARD_ID = "dashboard_id"
DASHBOARD_PATH = "dashboard_url_path"
DEFAULT_PATH = "mock-energy-lab"


def dashboard_collection(hass: HomeAssistant) -> DashboardsCollection:
    """Reuse HA's live collection instead of opening a competing storage writer."""
    # HA 2026.6 exposes this collection through its bound WebSocket list handler.
    # Keep that internal compatibility boundary isolated and fail safely if it changes.
    handler = hass.data.get(websocket_api.DOMAIN, {}).get(
        "lovelace/dashboards/list", (None,)
    )[0]
    owner = getattr(handler, "__self__", None)
    if isinstance(owner, DashboardsCollectionWebSocket) and isinstance(
        owner.storage_collection, DashboardsCollection
    ):
        return owner.storage_collection
    msg = "Home Assistant's editable dashboard collection is unavailable"
    raise HomeAssistantError(msg)


def _load_template() -> dict[str, Any]:
    """Load the bundled asset in an executor rather than blocking the event loop."""
    return json.loads(Path(__file__).with_name("dashboard.json").read_text())


class MockSolarDashboard:
    """Manage only the dashboard recorded by this integration entry."""

    def __init__(self, hass: HomeAssistant, entry: MockSolarConfigEntry) -> None:
        """Keep dashboard metadata separate from volatile simulation state."""
        self.hass = hass
        self.entry = entry
        self._lock = asyncio.Lock()

    async def _ready(self) -> None:
        """Initialize Lovelace only when the optional dashboard is requested."""
        if LOVELACE_DATA not in self.hass.data and not await async_setup_component(
            self.hass, "lovelace", {}
        ):
            msg = "Unable to initialize Home Assistant dashboards"
            raise HomeAssistantError(msg)

    def _existing(self) -> LovelaceStorage | None:
        """Locate the recorded dashboard without adopting unrelated panels."""
        path = self.entry.data.get(DASHBOARD_PATH)
        dashboard = self.hass.data[LOVELACE_DATA].dashboards.get(path)
        if (
            isinstance(dashboard, LovelaceStorage)
            and dashboard.config
            and dashboard.config.get("id") == self.entry.data.get(DASHBOARD_ID)
        ):
            return dashboard
        return None

    async def _configuration(self) -> dict[str, Any]:
        """Resolve every bundled entity reference using the actual registry IDs."""
        template = await self.hass.async_add_executor_job(_load_template)
        prefix = f"{self.entry.entry_id}_"
        mapping = {}
        for entity in er.async_entries_for_config_entry(
            er.async_get(self.hass), self.entry.entry_id
        ):
            if entity.unique_id.startswith(prefix):
                domain = entity.entity_id.split(".", 1)[0]
                key = entity.unique_id.removeprefix(prefix)
                mapping[f"{domain}.mock_{key}"] = entity.entity_id

        def resolve(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            if isinstance(value, str):
                if value in mapping:
                    return mapping[value]
                domain, separator, object_id = value.partition(".")
                if (
                    separator
                    and domain
                    in {"sensor", "binary_sensor", "number", "switch", "button"}
                    and object_id.startswith("mock_")
                ):
                    msg = f"Dashboard entity is not registered: {value}"
                    raise HomeAssistantError(msg)
            return value

        config = resolve(template)
        config[DOMAIN] = {"entry_id": self.entry.entry_id}
        return config

    async def async_ensure(self, *, regenerate: bool = False) -> None:
        """Create once, or explicitly replace the owned dashboard's layout."""
        if not self.entry.options.get(CONF_CREATE_DASHBOARD, False):
            if regenerate:
                msg = "Enable Create dashboard in Mock Solar options first"
                raise HomeAssistantError(msg)
            return
        async with self._lock:
            await self._ready()
            existing = self._existing()
            if existing is not None:
                if not regenerate:
                    return
                previous = await existing.async_load(force=False)
                if previous.get(DOMAIN) != {"entry_id": self.entry.entry_id}:
                    msg = (
                        "Dashboard ownership cannot be verified; "
                        "existing content was preserved"
                    )
                    raise HomeAssistantError(msg)
                await existing.async_save(await self._configuration())
                return

            config = await self._configuration()
            path = DEFAULT_PATH
            suffix = 2
            dashboards = self.hass.data[LOVELACE_DATA].dashboards
            while path in dashboards or frontend.async_panel_exists(self.hass, path):
                path = f"{DEFAULT_PATH}-{suffix}"
                suffix += 1
            collection = dashboard_collection(self.hass)
            item = await collection.async_create_item(
                {
                    "title": "Energy Lab",
                    "icon": "mdi:solar-power",
                    "url_path": path,
                    "show_in_sidebar": True,
                    "require_admin": False,
                }
            )
            try:
                await dashboards[path].async_save(config)
            except HomeAssistantError, OSError, ValueError:
                await collection.async_delete_item(item["id"])
                raise
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    **self.entry.data,
                    DASHBOARD_ID: item["id"],
                    DASHBOARD_PATH: path,
                },
            )
