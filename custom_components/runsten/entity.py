"""The entities of a vehicle, and what reads the core's State."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import RunstenConfigEntry, RunstenCoordinator

type State = dict[str, Any]


class RunstenEntity(CoordinatorEntity[RunstenCoordinator]):
    """An entity of a vehicle, in its device; unavailable while Runsten does not answer."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RunstenCoordinator,
        vehicle_id: str,
        description: EntityDescription,
    ) -> None:
        """Make the entity of description for the vehicle."""
        super().__init__(coordinator)
        self.entity_description = description
        self.vehicle_id = vehicle_id
        # Unique among the integration's: MQTT's discovery has its own (runsten_<id>_…),
        # so that a user who has both sees two devices.
        self._attr_unique_id = f"{vehicle_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, vehicle_id)})

    @property
    def available(self) -> bool:
        """Whether Runsten answers, with the vehicle's state."""
        return super().available and self.vehicle_id in self.coordinator.data.states

    @property
    def state_data(self) -> State:
        """The vehicle's latest state (the core's State)."""
        return self.coordinator.data.states[self.vehicle_id]


def async_add_vehicle_entities[D: EntityDescription](
    entry: RunstenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    descriptions: Iterable[D],
    exists: Callable[[D, State], bool],
    make: Callable[[RunstenCoordinator, str, D], RunstenEntity],
) -> None:
    """Add each vehicle's entities that it tells, and those it comes to tell.

    An entity is added once its vehicle tells its value (exists), as MQTT's discovery
    configures the climate's and the openings' only for a vehicle that tells them; a
    vehicle added to the account gets its entities at the next refresh.
    """
    coordinator = entry.runtime_data
    descriptions = list(descriptions)
    added: set[tuple[str, str]] = set()

    @callback
    def add() -> None:
        new: list[RunstenEntity] = []
        for vehicle_id in coordinator.data.vehicles:
            state = coordinator.data.states.get(vehicle_id)
            if state is None:
                continue
            for description in descriptions:
                key = (vehicle_id, description.key)
                if key not in added and exists(description, state):
                    added.add(key)
                    new.append(make(coordinator, vehicle_id, description))
        if new:
            async_add_entities(new)

    add()
    entry.async_on_unload(coordinator.async_add_listener(add))


def reading(state: State, *path: str) -> Any:
    """Return the value of the reading at path in the state; None when unknown."""
    node: Any = state
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if not isinstance(node, dict):
        return None
    return node.get("value")


def checked_at(state: State, *path: str) -> datetime | None:
    """Return when the reading at path was last read; None when it never was."""
    node: Any = state
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    if isinstance(node, dict) and node.get("checked_at"):
        return dt_util.parse_datetime(node["checked_at"])
    return None


def tells_climate(state: State) -> bool:
    """Whether the vehicle tells its temperatures and climate (a Tesla)."""
    climate = state.get("climate") or {}
    return any(v is not None for v in climate.values())


def part(state: State, group: str, key: str) -> Any:
    """Return a door's, a window's or the lock's value; None when not told."""
    value = reading(state, group)
    return value.get(key) if isinstance(value, dict) else None
