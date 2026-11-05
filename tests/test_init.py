"""Tests of the entities, the coordinator and the repair of Free."""

from __future__ import annotations

import copy

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_TOKEN,
    CONF_URL,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.runsten.const import CONF_HOSTED, CONF_TRACK_LOCATION, DOMAIN
from custom_components.runsten.coordinator import labels

from .conftest import (
    STATES,
    TESLA_ID,
    TOKEN,
    VEHICLES,
    VIN,
    VOLVO_ID,
    hosted_entry,
    mock_hosted,
    setup,
)


def _device(
    hass: HomeAssistant, entry: MockConfigEntry, vehicle_id: str
) -> dr.DeviceEntry | None:
    """The vehicle's device in the entry, None when there is none."""
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        if (DOMAIN, vehicle_id) in device.identifiers:
            return device
    return None


def _state(hass: HomeAssistant, platform: str, vehicle_id: str, key: str) -> str | None:
    """The state of a vehicle's entity, None when it was not added."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{vehicle_id}_{key}"
    )
    if entity_id is None:
        return None
    return hass.states.get(entity_id).state


async def test_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Each vehicle's values; unknown when Runsten does not know them, never zero."""
    mock_hosted(aioclient_mock)
    await setup(hass, hosted_entry())

    def volvo(platform: str, key: str) -> str | None:
        return _state(hass, platform, VOLVO_ID, key)

    def tesla(platform: str, key: str) -> str | None:
        return _state(hass, platform, TESLA_ID, key)

    assert volvo("sensor", "battery_level") == "72.5"
    assert volvo("sensor", "range") == "310"
    assert volvo("sensor", "charging_status") == "idle"
    assert volvo("sensor", "charge_type") == "none"
    assert volvo("sensor", "charging_power") == STATE_UNKNOWN
    assert volvo("sensor", "target_soc") == "90"
    assert volvo("sensor", "odometer") == "12345"
    assert volvo("sensor", "read_at") == "2026-11-04T08:00:00+00:00"
    assert volvo("binary_sensor", "plug") == STATE_OFF
    assert volvo("binary_sensor", "charging") == STATE_OFF
    assert volvo("binary_sensor", "engine") == STATE_OFF
    assert volvo("device_tracker", "location") == "not_home"
    # What a Volvo does not tell has no entity.
    for platform, key in (
        ("sensor", "outside_temperature"),
        ("sensor", "openings_read_at"),
        ("binary_sensor", "climate"),
        ("binary_sensor", "lock"),
        ("binary_sensor", "credential"),
    ):
        assert volvo(platform, key) is None, key

    assert tesla("sensor", "battery_level") == STATE_UNKNOWN
    assert tesla("sensor", "odometer") == STATE_UNKNOWN
    assert tesla("sensor", "charging_status") == "charging"
    assert tesla("sensor", "charge_type") == "ac"
    assert tesla("sensor", "charging_power") == "7.4"
    assert tesla("binary_sensor", "charging") == STATE_ON
    assert tesla("binary_sensor", "plug") == STATE_UNKNOWN  # a cable fault
    assert tesla("binary_sensor", "engine") == STATE_UNKNOWN
    assert tesla("binary_sensor", "credential") == STATE_ON
    assert tesla("sensor", "outside_temperature") == "4.5"
    assert tesla("sensor", "cabin_temperature") == STATE_UNKNOWN
    assert tesla("binary_sensor", "climate") == STATE_ON
    assert tesla("binary_sensor", "preconditioning") == STATE_OFF
    assert tesla("binary_sensor", "battery_heater") == STATE_UNKNOWN
    assert tesla("binary_sensor", "lock") == STATE_ON  # unlocked
    assert tesla("binary_sensor", "door_front_left") == STATE_OFF
    assert tesla("binary_sensor", "tailgate") == STATE_ON
    assert tesla("binary_sensor", "window_front_left") == STATE_ON  # ajar
    assert tesla("binary_sensor", "sentry") == STATE_ON
    assert tesla("sensor", "openings_read_at") == "2026-11-04T07:00:00+00:00"
    assert tesla("binary_sensor", "door_front_right") is None
    assert tesla("binary_sensor", "sunroof") is None
    assert tesla("device_tracker", "location") == STATE_UNKNOWN


async def test_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A device per vehicle, named as the web interface does, never by its VIN.

    Its software version is the vehicle's, where the vehicle tells it.
    """
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)

    volvo = _device(hass, entry, VOLVO_ID)
    assert volvo.name == "EX30 Single Motor Extended Range · 2025"
    assert volvo.manufacturer == "Volvo"
    assert volvo.model == "EX30 Single Motor Extended Range"
    tesla = _device(hass, entry, TESLA_ID)
    assert tesla.name == "Blixten"
    assert tesla.manufacturer == "Tesla"
    assert tesla.sw_version == "2026.38.6"
    assert volvo.sw_version is None
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        assert VIN not in str(device)


def test_labels() -> None:
    """Two vehicles that read alike end with the first characters of their ID."""
    a = copy.deepcopy(VEHICLES[0])
    b = copy.deepcopy(a) | {"id": "ffeedd00-0000-4000-8000-000000000003"}
    bare = copy.deepcopy(a) | {"id": "abcdef12-0000", "model": {"family": None}}
    names = labels({v["id"]: v for v in (a, b, bare)})
    assert names[a["id"]] == "EX30 Single Motor Extended Range · 2025 · 0b1c2d"
    assert names[b["id"]] == "EX30 Single Motor Extended Range · 2025 · ffeedd"
    assert names[bare["id"]] == "Volvo abcdef"


async def test_free_repair(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A Free account gets one repair, with the offer's link; gone once in Plus."""
    mock_hosted(aioclient_mock, plan="free")
    entry = hosted_entry()
    await setup(hass, entry)

    issue_id = f"free_plan_{entry.entry_id}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.learn_more_url == "https://my.runsten.app/offer"
    assert issue.translation_placeholders == {"minutes": "60"}
    assert not issue.is_fixable

    # In Plus, read again with the details: the repair goes.
    aioclient_mock.clear_requests()
    mock_hosted(aioclient_mock, plan="plus")
    coordinator = entry.runtime_data
    coordinator._details_at = None
    await coordinator.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_plus_no_repair(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Plus has no repair."""
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)
    assert not ir.async_get(hass).issues


async def test_one_request_a_minute(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Once set up, a refresh is one request: every vehicle's state."""
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)
    calls = aioclient_mock.call_count
    await entry.runtime_data.async_refresh()
    assert aioclient_mock.call_count == calls + 1
    assert str(aioclient_mock.mock_calls[-1][1]).endswith("/states")


async def test_unavailable_then_back(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The entities are unavailable while Runsten does not answer."""
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)
    coordinator = entry.runtime_data

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        "https://my.runsten.app/api/cloud/homeassistant/states", status=503
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", VOLVO_ID, "battery_level") == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    mock_hosted(aioclient_mock)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", VOLVO_ID, "battery_level") == "72.5"


async def test_token_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A token refused while running asks for another."""
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        "https://my.runsten.app/api/cloud/homeassistant/states", status=401
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_token_refused_at_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A token refused at setup leaves the entry in error, asking for another."""
    aioclient_mock.get(
        "https://my.runsten.app/api/cloud/homeassistant/states", status=401
    )
    entry = hosted_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_vehicle_added_and_removed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A vehicle added gets its entities at the next refresh; one removed, its device goes."""
    mock_hosted(aioclient_mock, vehicles=VEHICLES[:1], states=STATES[:1])
    entry = hosted_entry()
    await setup(hass, entry)
    assert _state(hass, "sensor", TESLA_ID, "range") is None

    aioclient_mock.clear_requests()
    mock_hosted(aioclient_mock)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", TESLA_ID, "range") == STATE_UNKNOWN

    aioclient_mock.clear_requests()
    mock_hosted(aioclient_mock, vehicles=VEHICLES[1:], states=STATES[1:])
    entry.runtime_data._details_at = None
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _device(hass, entry, VOLVO_ID) is None
    assert _device(hass, entry, TESLA_ID) is not None


async def test_location_off(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Without the position, no tracker; those added before are removed."""
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)
    assert _state(hass, "device_tracker", VOLVO_ID, "location") == "not_home"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TRACK_LOCATION: False}
    )
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, "device_tracker", VOLVO_ID, "location") is None
    assert not hass.states.async_entity_ids("device_tracker")


async def test_custom_instance(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A self-hosted instance is read through the core's API, without a repair."""
    base = "https://runsten.example.org/api/v1/"
    aioclient_mock.get(base + "vehicles", json={"items": copy.deepcopy(VEHICLES)})
    for state in STATES:
        aioclient_mock.get(
            f"{base}vehicles/{state['vehicle_id']}/state", json=copy.deepcopy(state)
        )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="runsten.example.org",
        data={
            CONF_URL: "https://runsten.example.org",
            CONF_TOKEN: TOKEN,
            CONF_HOSTED: False,
        },
    )
    await setup(hass, entry)
    assert _state(hass, "sensor", VOLVO_ID, "battery_level") == "72.5"
    assert _state(hass, "binary_sensor", TESLA_ID, "tailgate") == STATE_ON
    assert not ir.async_get(hass).issues
    assert not any("/api/cloud/" in str(c[1]) for c in aioclient_mock.mock_calls)
