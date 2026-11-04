"""Tests of the configuration flow."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.runsten.const import (
    CONF_HOSTED,
    CONF_TRACK_LOCATION,
    DOMAIN,
    SECTION_ADVANCED,
)

from .conftest import HOSTED, TOKEN, URL, hosted_entry, mock_hosted, setup


def _input(token: str = TOKEN, url: str = URL) -> dict:
    return {CONF_TOKEN: token, SECTION_ADVANCED: {CONF_URL: url}}


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def test_hosted(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A token of my.runsten.app, the default URL, makes an entry of the hosted offer."""
    mock_hosted(aioclient_mock)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, _input(f" {TOKEN} ")
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "my.runsten.app"
    assert result["data"] == {CONF_URL: URL, CONF_TOKEN: TOKEN, CONF_HOSTED: True}
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_custom_instance(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An instance that does not know the hosted API is read through the core's."""
    base = "https://runsten.example.org"
    aioclient_mock.get(base + "/api/cloud/homeassistant/account", status=404)
    aioclient_mock.get(base + "/api/v1/vehicles", json={"items": []})
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, _input(url="runsten.example.org/")
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "runsten.example.org"
    assert result["data"] == {CONF_URL: base, CONF_TOKEN: TOKEN, CONF_HOSTED: False}


async def test_errors_then_success(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Each error is told on the form, which can be sent again."""
    flow_id = await _start(hass)

    result = await hass.config_entries.flow.async_configure(flow_id, _input("abc"))
    assert result["errors"] == {CONF_TOKEN: "invalid_token"}

    result = await hass.config_entries.flow.async_configure(
        flow_id, _input(url="ftp://example.org")
    )
    assert result["errors"] == {"base": "invalid_url"}

    aioclient_mock.get(HOSTED + "account", status=401)
    result = await hass.config_entries.flow.async_configure(flow_id, _input())
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(HOSTED + "account", exc=aiohttp.ClientConnectionError())
    result = await hass.config_entries.flow.async_configure(flow_id, _input())
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(HOSTED + "account", status=404)
    aioclient_mock.get(URL + "/api/v1/vehicles", status=404)
    result = await hass.config_entries.flow.async_configure(flow_id, _input())
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_hosted(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(flow_id, _input())
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The same token of the same instance is connected once."""
    hosted_entry().add_to_hass(hass)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(flow_id, _input())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A new token replaces the one refused."""
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "rst_new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "rst_new"
    assert entry.data[CONF_URL] == URL


async def test_options(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The position can be turned off."""
    mock_hosted(aioclient_mock)
    entry = hosted_entry()
    await setup(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TRACK_LOCATION: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_TRACK_LOCATION: False}
