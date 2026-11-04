"""The position of each vehicle, unless turned off in the options."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_TRACK_LOCATION, DEFAULT_TRACK_LOCATION
from .coordinator import RunstenConfigEntry
from .entity import RunstenEntity, async_add_vehicle_entities, reading

PARALLEL_UPDATES = 0

LOCATION = EntityDescription(key="location", translation_key="location")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunstenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add each vehicle's tracker; without the position, remove those added before."""
    if not entry.options.get(CONF_TRACK_LOCATION, DEFAULT_TRACK_LOCATION):
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.domain == Platform.DEVICE_TRACKER:
                registry.async_remove(entity.entity_id)
        return
    async_add_vehicle_entities(
        entry, async_add_entities, (LOCATION,), lambda _d, _s: True, RunstenTracker
    )


class RunstenTracker(RunstenEntity, TrackerEntity):
    """The vehicle's latest known position; unknown when Runsten has none."""

    _attr_source_type = SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """The latitude of the latest position."""
        position = reading(self.state_data, "position")
        return position["lat"] if position else None

    @property
    def longitude(self) -> float | None:
        """The longitude of the latest position."""
        position = reading(self.state_data, "position")
        return position["lon"] if position else None
