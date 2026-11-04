"""The coordinator: the state of every vehicle of the account, once a minute."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Account,
    RunstenAuthError,
    RunstenClient,
    RunstenError,
    RunstenRateLimitedError,
)
from .const import DETAILS_INTERVAL, DOMAIN, ISSUE_FREE, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type RunstenConfigEntry = ConfigEntry[RunstenCoordinator]

# The brand of a vehicle, from the provider of the connection that reads it.
BRANDS = {
    "volvo": "Volvo",
    "polestar": "Polestar",
    "polestar_id": "Polestar",
    "tesla": "Tesla",
    "tesla_fleet": "Tesla",
}

# The characters of a vehicle's ID that tell it apart where nothing else does.
ID_DIGITS = 6


@dataclass
class RunstenData:
    """What the coordinator read of the account."""

    account: Account | None = None
    # The vehicles (the core's Vehicle) and their states (State), by vehicle ID.
    vehicles: dict[str, dict[str, Any]] = field(default_factory=dict)
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Each vehicle's name, as the web interface gives it (labels).
    labels: dict[str, str] = field(default_factory=dict)


class RunstenCoordinator(DataUpdateCoordinator[RunstenData]):
    """Reads the states of the account's vehicles; their details and its offer hourly."""

    config_entry: RunstenConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: RunstenConfigEntry, client: RunstenClient
    ) -> None:
        """Poll the account through client once a minute."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._details_at: datetime | None = None

    async def _async_update_data(self) -> RunstenData:
        previous = self.data or RunstenData()
        try:
            states = {s["vehicle_id"]: s for s in await self.client.states()}
            now = dt_util.utcnow()
            if (
                self._details_at is None
                or now - self._details_at >= DETAILS_INTERVAL
                or not states.keys() <= previous.vehicles.keys()
            ):
                account = await self.client.account()
                vehicles = {v["id"]: v for v in await self.client.vehicles()}
                self._details_at = now
                data = RunstenData(account, vehicles, states, labels(vehicles))
                self._details_changed(data)
                return data
        except RunstenAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except RunstenRateLimitedError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="rate_limited"
            ) from err
        except RunstenError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        return RunstenData(previous.account, previous.vehicles, states, previous.labels)

    def _details_changed(self, data: RunstenData) -> None:
        """Name the devices, remove those of the vehicles gone, and tell a Free account."""
        entry = self.config_entry
        registry = dr.async_get(self.hass)
        for vehicle_id, vehicle in data.vehicles.items():
            registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, vehicle_id)},
                name=data.labels[vehicle_id],
                manufacturer=brand(vehicle),
                model=model_name(vehicle),
            )
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            if not any(
                d == DOMAIN and i in data.vehicles for d, i in device.identifiers
            ):
                registry.async_remove_device(device.id)

        issue_id = f"{ISSUE_FREE}_{entry.entry_id}"
        if data.account is not None and data.account.free:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                is_persistent=False,
                learn_more_url=data.account.offer_url,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_FREE,
                translation_placeholders={
                    "minutes": str(max(1, data.account.read_every_s // 60)),
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)


def brand(vehicle: dict[str, Any]) -> str | None:
    """Return the vehicle's brand, as written."""
    return BRANDS.get(vehicle.get("connection", {}).get("provider", ""))


def model_name(vehicle: dict[str, Any]) -> str | None:
    """Return what the vehicle is: the variant in effect, else the family."""
    model = vehicle.get("model") or {}
    variant = model.get("variant") or {}
    return variant.get("name") or model.get("family")


def label(vehicle: dict[str, Any]) -> str:
    """Name the vehicle as the web interface does, never by its VIN.

    The name its owner gave it, else the variant or the family with the model year;
    before its details are read, the brand and the first characters of its ID.
    """
    sheet = vehicle.get("sheet") or {}
    if sheet.get("name"):
        return sheet["name"]
    name = model_name(vehicle)
    if not name:
        return f"{brand(vehicle) or 'Runsten'} {vehicle['id'][:ID_DIGITS]}"
    year = (vehicle.get("model") or {}).get("model_year")
    return f"{name} · {year}" if year else name


def labels(vehicles: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Name the vehicles: two that read alike end with the first characters of their ID."""
    names = {vehicle_id: label(v) for vehicle_id, v in vehicles.items()}
    count = Counter(names.values())
    return {
        vehicle_id: f"{name} · {vehicle_id[:ID_DIGITS]}" if count[name] > 1 else name
        for vehicle_id, name in names.items()
    }
