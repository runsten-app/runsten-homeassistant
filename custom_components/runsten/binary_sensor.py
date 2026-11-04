"""The binary sensors of a vehicle: plug, charge, engine, climate, lock, doors, windows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import RunstenConfigEntry
from .entity import (
    RunstenEntity,
    State,
    async_add_vehicle_entities,
    part,
    reading,
    tells_climate,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class RunstenBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor of a vehicle: on, off or None (unknown), and whether it tells it."""

    value_fn: Callable[[State], bool | None]
    exists_fn: Callable[[State], bool] = lambda _: True


def _on_off(value: Any, on: Any, off: Any) -> bool | None:
    """On for on, off for off, unknown for any other value (a cable fault)."""
    if value == on:
        return True
    if value == off:
        return False
    return None


def _charging(status: str | None) -> bool | None:
    """Whether the vehicle charges: unknown only when its status is."""
    return None if status is None else status == "charging"


def _credential_problem(state: State) -> bool | None:
    """Return a problem while the credential is not valid (refused, or removed)."""
    credential = (state.get("connection") or {}).get("credential")
    return None if credential is None else credential != "set"


# The four doors' keys, and the four windows'.
DOORS = ("front_left", "front_right", "rear_left", "rear_right")


def _open(value: str | None) -> bool | None:
    """Return whether a door, a lid or a window is open or ajar."""
    return None if value is None else value != "closed"


def _part(
    key: str,
    group: str,
    field: str,
    device_class: BinarySensorDeviceClass | None,
    value_fn: Callable[[Any], bool | None],
) -> RunstenBinarySensorDescription:
    """Describe the lock, a door, a lid, a window or Sentry Mode, configured where told."""
    return RunstenBinarySensorDescription(
        key=key,
        translation_key=key,
        device_class=device_class,
        value_fn=lambda s: value_fn(part(s, group, field)),
        exists_fn=lambda s: part(s, group, field) is not None,
    )


BINARY_SENSORS: tuple[RunstenBinarySensorDescription, ...] = (
    RunstenBinarySensorDescription(
        key="plug",
        translation_key="plug",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda s: _on_off(
            reading(s, "charging", "cable"), "connected", "disconnected"
        ),
    ),
    RunstenBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda s: _charging(reading(s, "charging", "status")),
    ),
    RunstenBinarySensorDescription(
        key="engine",
        translation_key="engine",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: _on_off(reading(s, "engine"), "running", "stopped"),
    ),
    RunstenBinarySensorDescription(
        key="credential",
        translation_key="credential",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_credential_problem,
        exists_fn=lambda s: _credential_problem(s) is not None,
    ),
    RunstenBinarySensorDescription(
        key="climate",
        translation_key="climate",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: reading(s, "climate", "on"),
        exists_fn=tells_climate,
    ),
    RunstenBinarySensorDescription(
        key="preconditioning",
        translation_key="preconditioning",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: reading(s, "climate", "preconditioning"),
        exists_fn=tells_climate,
    ),
    RunstenBinarySensorDescription(
        key="battery_heater",
        translation_key="battery_heater",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: reading(s, "climate", "battery_heater"),
        exists_fn=tells_climate,
    ),
    # The lock: on (unsafe) when unlocked, as Home Assistant's lock device class.
    _part(
        "lock",
        "doors",
        "locked",
        BinarySensorDeviceClass.LOCK,
        lambda locked: None if locked is None else not locked,
    ),
    *(
        _part(f"door_{k}", "doors", k, BinarySensorDeviceClass.DOOR, _open)
        for k in DOORS
    ),
    _part("hood", "doors", "hood", BinarySensorDeviceClass.OPENING, _open),
    _part("tailgate", "doors", "tailgate", BinarySensorDeviceClass.OPENING, _open),
    _part("tank_lid", "doors", "tank_lid", BinarySensorDeviceClass.OPENING, _open),
    *(
        _part(f"window_{k}", "windows", k, BinarySensorDeviceClass.WINDOW, _open)
        for k in DOORS
    ),
    _part("sunroof", "windows", "sunroof", BinarySensorDeviceClass.WINDOW, _open),
    _part("sentry", "doors", "sentry", None, lambda on: on),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunstenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors of each vehicle."""
    async_add_vehicle_entities(
        entry,
        async_add_entities,
        BINARY_SENSORS,
        lambda d, s: d.exists_fn(s),
        RunstenBinarySensor,
    )


class RunstenBinarySensor(RunstenEntity, BinarySensorEntity):
    """A binary sensor of a vehicle; unknown when Runsten does not know its value."""

    entity_description: RunstenBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """On, off, or None (unknown): never off for want of a reading."""
        return self.entity_description.value_fn(self.state_data)
