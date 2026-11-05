"""Fixtures of the Runsten integration's tests: an account with a Volvo and a Tesla."""

from __future__ import annotations

import copy
import time
from typing import Any

from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.runsten.const import CONF_HOSTED, DOMAIN

URL = "https://my.runsten.app"
HOSTED = URL + "/api/cloud/homeassistant/"
TOKEN = "rst_0123456789abcdef"

ACCOUNT_ID = "5a1c0000-0000-4000-8000-0000000000aa"
# The tokens of a sign-in with Runsten.
ACCESS_TOKEN = "rso_access"
REFRESH_TOKEN = "rsr_refresh"

VOLVO_ID = "0b1c2d3e-0000-4000-8000-000000000001"
TESLA_ID = "7e5a1a00-0000-4000-8000-000000000002"
VIN = "YV1XZK9V0R2000001"

AT = "2026-11-04T08:00:00Z"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


def _reading(value: Any, checked: str = AT) -> dict[str, Any]:
    return {
        "value": value,
        "reported_at": None,
        "fetched_at": AT,
        "checked_at": checked,
    }


def _connection(provider: str, credential: str | None) -> dict[str, Any]:
    return {
        "provider": provider,
        "status": "active",
        "api_key": None,
        "credential": credential,
        "authorized_at": None,
        "refreshed_at": None,
        "reauth_at": None,
        "reauth_reason": None,
    }


def _model(family: str | None, variant: str | None, year: int | None) -> dict[str, Any]:
    return {
        "family": family,
        "model_year": year,
        "variant": None if variant is None else {"id": "x", "name": variant},
        "variant_source": None,
        "ac_max_kw": None,
        "powertrain": "electric",
    }


VEHICLES: list[dict[str, Any]] = [
    {
        "id": VOLVO_ID,
        "vin": VIN,
        "model": _model("EX30", "EX30 Single Motor Extended Range", 2025),
        "sheet": None,
        "connection": _connection("volvo", None),
        "market_refused_at": None,
        "unshared_at": None,
        "collection": None,
    },
    {
        "id": TESLA_ID,
        "vin": "5YJ3E7EB0KF000002",
        "model": _model("Model 3", None, 2019),
        "sheet": {"name": "Blixten"},
        "connection": _connection("tesla", "refused"),
        "market_refused_at": None,
        "unshared_at": None,
        "collection": None,
    },
]

_NO_CLIMATE = {
    "outside_temp_c": None,
    "cabin_temp_c": None,
    "on": None,
    "preconditioning": None,
    "battery_heater": None,
}


def _charging(**values: Any) -> dict[str, Any]:
    charging = dict.fromkeys(
        (
            "status",
            "cable",
            "type",
            "power_w",
            "target_soc_pct",
            "current_a",
            "voltage_v",
            "phases",
            "current_limit_a",
            "time_left",
            "charger",
        )
    )
    charging.update({k: _reading(v) for k, v in values.items()})
    return charging


STATES: list[dict[str, Any]] = [
    {
        "vehicle_id": VOLVO_ID,
        "connection": _connection("volvo", None),
        "checked_at": AT,
        "engine": _reading("stopped"),
        "soc_pct": _reading(72.5),
        "range_km": _reading(310),
        "odometer_km": _reading(12345),
        "position": _reading({"lat": 59.33, "lon": 18.06}),
        "battery_capacity_kwh": None,
        "charging": _charging(
            status="idle", cable="disconnected", type="none", target_soc_pct=90
        ),
        "climate": _NO_CLIMATE,
        "software": None,
        "software_update": None,
        "doors": None,
        "windows": None,
        "sleep": None,
    },
    {
        "vehicle_id": TESLA_ID,
        "connection": _connection("tesla", "refused"),
        "checked_at": AT,
        "engine": None,
        "soc_pct": None,
        "range_km": None,
        "odometer_km": None,
        "position": None,
        "battery_capacity_kwh": None,
        "charging": _charging(
            status="charging", cable="fault", type="AC", power_w=7400
        ),
        "climate": {
            "outside_temp_c": _reading(4.5),
            "cabin_temp_c": None,
            "on": _reading(True),
            "preconditioning": _reading(False),
            "battery_heater": None,
        },
        "software": _reading("2026.38.6"),
        "software_update": None,
        "doors": _reading(
            {
                "locked": False,
                "front_left": "closed",
                "front_right": None,
                "rear_left": None,
                "rear_right": None,
                "hood": None,
                "tailgate": "open",
                "tank_lid": None,
                "sentry": True,
            },
            checked="2026-11-04T07:00:00Z",
        ),
        "windows": _reading(
            {
                "front_left": "ajar",
                "front_right": None,
                "rear_left": None,
                "rear_right": None,
                "sunroof": None,
            }
        ),
        "sleep": None,
    },
]


def account(plan: str = "plus") -> dict[str, Any]:
    """The hosted account's offer."""
    return {
        "account_id": ACCOUNT_ID,
        "plan": plan,
        "plus_until": "2027-11-04T00:00:00Z" if plan == "plus" else None,
        "read_every_s": 60 if plan == "plus" else 3600,
        "offer_url": "https://my.runsten.app/offer",
    }


def mock_hosted(
    aioclient_mock: AiohttpClientMocker,
    *,
    plan: str = "plus",
    vehicles: list[dict[str, Any]] | None = None,
    states: list[dict[str, Any]] | None = None,
) -> None:
    """Answer the hosted API's routes."""
    aioclient_mock.get(HOSTED + "account", json=account(plan))
    aioclient_mock.get(
        HOSTED + "vehicles",
        json={"items": copy.deepcopy(VEHICLES if vehicles is None else vehicles)},
    )
    aioclient_mock.get(
        HOSTED + "states",
        json={"items": copy.deepcopy(STATES if states is None else states)},
    )


def hosted_entry(**options: Any) -> MockConfigEntry:
    """A configuration entry of the hosted offer."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="my.runsten.app",
        data={CONF_URL: URL, CONF_TOKEN: TOKEN, CONF_HOSTED: True},
        options=options,
    )


def oauth_entry(expires_in: float = 3600, **options: Any) -> MockConfigEntry:
    """A configuration entry signed in with Runsten, its access token valid so long."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="my.runsten.app",
        unique_id=ACCOUNT_ID,
        data={
            "auth_implementation": DOMAIN,
            "token": {
                "access_token": ACCESS_TOKEN,
                "refresh_token": REFRESH_TOKEN,
                "token_type": "Bearer",
                "expires_in": 3600,
                "expires_at": time.time() + expires_in,
            },
            CONF_URL: URL,
            CONF_HOSTED: True,
        },
        options=options,
    )


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set the entry up."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
