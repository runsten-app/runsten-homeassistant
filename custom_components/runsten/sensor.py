"""The sensors of a vehicle: battery, range, charge, odometer, temperatures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import RunstenConfigEntry
from .entity import (
    RunstenEntity,
    State,
    async_add_vehicle_entities,
    checked_at,
    reading,
    tells_climate,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class RunstenSensorDescription(SensorEntityDescription):
    """A sensor of a vehicle: its value in the state, and whether the vehicle tells it."""

    value_fn: Callable[[State], StateType | datetime]
    exists_fn: Callable[[State], bool] = lambda _: True


def _lower(value: str | None) -> str | None:
    return value.lower() if value is not None else None


def _kw(watts: float | None) -> float | None:
    return watts / 1000 if watts is not None else None


def _openings_read_at(state: State) -> datetime | None:
    """When the doors and windows were last read, the older of the two."""
    read = [t for t in (checked_at(state, "doors"), checked_at(state, "windows")) if t]
    return min(read, default=None)


SENSORS: tuple[RunstenSensorDescription, ...] = (
    RunstenSensorDescription(
        key="battery_level",
        suggested_display_precision=0,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: reading(s, "soc_pct"),
    ),
    RunstenSensorDescription(
        key="range",
        suggested_display_precision=0,
        translation_key="range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: reading(s, "range_km"),
    ),
    RunstenSensorDescription(
        key="charging_status",
        translation_key="charging_status",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "charging", "done", "scheduled", "discharging", "error"],
        value_fn=lambda s: reading(s, "charging", "status"),
    ),
    RunstenSensorDescription(
        key="charge_type",
        translation_key="charge_type",
        device_class=SensorDeviceClass.ENUM,
        options=["ac", "dc", "none"],
        value_fn=lambda s: _lower(reading(s, "charging", "type")),
    ),
    RunstenSensorDescription(
        key="charging_power",
        suggested_display_precision=1,
        translation_key="charging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: _kw(reading(s, "charging", "power_w")),
    ),
    RunstenSensorDescription(
        key="target_soc",
        translation_key="target_soc",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda s: reading(s, "charging", "target_soc_pct"),
    ),
    RunstenSensorDescription(
        key="odometer",
        suggested_display_precision=0,
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: reading(s, "odometer_km"),
    ),
    RunstenSensorDescription(
        key="read_at",
        translation_key="read_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: checked_at(s),
    ),
    RunstenSensorDescription(
        key="outside_temperature",
        suggested_display_precision=1,
        translation_key="outside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: reading(s, "climate", "outside_temp_c"),
        exists_fn=tells_climate,
    ),
    RunstenSensorDescription(
        key="cabin_temperature",
        suggested_display_precision=1,
        translation_key="cabin_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: reading(s, "climate", "cabin_temp_c"),
        exists_fn=tells_climate,
    ),
    RunstenSensorDescription(
        key="openings_read_at",
        translation_key="openings_read_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_openings_read_at,
        exists_fn=lambda s: s.get("doors") is not None or s.get("windows") is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunstenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors of each vehicle."""
    async_add_vehicle_entities(
        entry,
        async_add_entities,
        SENSORS,
        lambda d, s: d.exists_fn(s),
        RunstenSensor,
    )


class RunstenSensor(RunstenEntity, SensorEntity):
    """A sensor of a vehicle; unknown when Runsten does not know its value."""

    entity_description: RunstenSensorDescription

    @property
    def native_value(self) -> StateType | datetime:
        """The value, None (unknown) when Runsten does not know it: never a zero."""
        return self.entity_description.value_fn(self.state_data)
