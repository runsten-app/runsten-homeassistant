"""Tests of signing in with Runsten: the OAuth 2 flow, the tokens' renewal, reauth."""

from __future__ import annotations

import base64
import hashlib
import time
from unittest.mock import Mock, patch

import aiohttp
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.config_entry_oauth2_flow import (
    MY_AUTH_CALLBACK_PATH,
    async_register_implementation,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from yarl import URL as YURL

from custom_components.runsten import _async_token_source
from custom_components.runsten.api import RunstenAuthError, RunstenConnectionError
from custom_components.runsten.const import (
    CONF_HOSTED,
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_RESOURCE,
    OAUTH_TOKEN_URL,
)
from custom_components.runsten.oauth import RunstenImplementation

from .conftest import (
    ACCESS_TOKEN,
    ACCOUNT_ID,
    HOSTED,
    REFRESH_TOKEN,
    URL,
    account,
    mock_hosted,
    oauth_entry,
    setup,
)

pytestmark = pytest.mark.usefixtures("current_request_with_host")


def _tokens(access: str = "rso_new", refresh: str = "rsr_new") -> dict:
    """A token response of Runsten's authorization server."""
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": refresh,
    }


async def _sign_in(
    hass: HomeAssistant,
    client: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    result: dict,
) -> dict:
    """Follow the authorization URL of an external step as Runsten and My Home
    Assistant would, then return the flow's result once the code is exchanged; check
    what was asked.
    """
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    flow_id = result["flow_id"]
    url = YURL(result["url"])
    assert str(url.with_query(None)) == OAUTH_AUTHORIZE_URL
    query = url.query
    assert query["response_type"] == "code"
    assert query["client_id"] == OAUTH_CLIENT_ID
    assert query["redirect_uri"] == MY_AUTH_CALLBACK_PATH
    assert query["resource"] == OAUTH_RESOURCE
    assert query["code_challenge_method"] == "S256"
    # Runsten carries the state through the sign-in: at most 255 characters.
    assert len(query["state"]) <= 255

    http = await client()
    resp = await http.get(f"/auth/external/callback?code=c0de&state={query['state']}")
    assert resp.status == 200

    aioclient_mock.post(OAUTH_TOKEN_URL, json=_tokens())
    result = await hass.config_entries.flow.async_configure(flow_id)

    token_request = next(c for c in aioclient_mock.mock_calls if c[0] == "POST")
    form = token_request[2]
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "c0de"
    assert form["client_id"] == OAUTH_CLIENT_ID
    assert form["redirect_uri"] == MY_AUTH_CALLBACK_PATH
    assert form["resource"] == OAUTH_RESOURCE
    assert "client_secret" not in form
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(form["code_verifier"].encode()).digest()
        )
        .decode()
        .rstrip("=")
    )
    assert challenge == query["code_challenge"]
    return result


async def _setup_failing(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set the entry up, which fails."""
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _start_oauth(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "oauth"}
    )
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    return result


async def test_sign_in(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Signing in makes an entry of the hosted offer, the account's, with its tokens."""
    mock_hosted(aioclient_mock)
    result = await _sign_in(
        hass, hass_client_no_auth, aioclient_mock, await _start_oauth(hass)
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "my.runsten.app"
    assert result["result"].unique_id == ACCOUNT_ID
    data = result["data"]
    assert data[CONF_URL] == URL
    assert data[CONF_HOSTED] is True
    assert data["auth_implementation"] == DOMAIN
    assert data["token"]["access_token"] == "rso_new"
    assert data["token"]["refresh_token"] == "rsr_new"
    account_call = next(
        c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/account")
    )
    assert account_call[3]["Authorization"] == "Bearer rso_new"


async def test_a_new_verifier_each_time(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Each sign-in has its own PKCE challenge."""
    challenges = set()
    for _ in range(2):
        result = await _start_oauth(hass)
        challenges.add(YURL(result["url"]).query["code_challenge"])
    assert len(challenges) == 2


async def test_sign_in_already_configured(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The same account is connected once."""
    oauth_entry().add_to_hass(hass)
    mock_hosted(aioclient_mock)
    result = await _sign_in(
        hass, hass_client_no_auth, aioclient_mock, await _start_oauth(hass)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_sign_in_refused(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The user denies on Runsten's consent page: no entry."""
    result = await _start_oauth(hass)
    flow_id = result["flow_id"]
    state = YURL(result["url"]).query["state"]
    http = await hass_client_no_auth()
    resp = await http.get(f"/auth/external/callback?error=access_denied&state={state}")
    assert resp.status == 200
    result = await hass.config_entries.flow.async_configure(flow_id)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "user_rejected_authorize"


async def test_renewal(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An expired access token is renewed before reading; the new tokens are kept."""
    mock_hosted(aioclient_mock)
    aioclient_mock.post(OAUTH_TOKEN_URL, json=_tokens("rso_renewed", "rsr_renewed"))
    entry = oauth_entry(expires_in=-10)
    await setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    renewal = next(c for c in aioclient_mock.mock_calls if c[0] == "POST")
    assert renewal[2] == {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": OAUTH_CLIENT_ID,
    }
    assert entry.data["token"]["access_token"] == "rso_renewed"
    assert entry.data["token"]["refresh_token"] == "rsr_renewed"
    reads = [c for c in aioclient_mock.mock_calls if c[0] == "GET"]
    assert reads
    assert all(c[3]["Authorization"] == "Bearer rso_renewed" for c in reads)


async def test_valid_token_not_renewed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A valid access token is used as is."""
    mock_hosted(aioclient_mock)
    entry = oauth_entry()
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert not [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert all(
        c[3]["Authorization"] == f"Bearer {ACCESS_TOKEN}"
        for c in aioclient_mock.mock_calls
    )


@pytest.mark.parametrize(
    ("status", "state", "reauth"),
    [
        (400, ConfigEntryState.SETUP_ERROR, True),
        (500, ConfigEntryState.SETUP_RETRY, False),
        (429, ConfigEntryState.SETUP_RETRY, False),
    ],
)
async def test_renewal_refused(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    state: ConfigEntryState,
    reauth: bool,
) -> None:
    """A renewal Runsten refuses (the grant revoked) asks to sign in again; a failure
    of Runsten, a timeout or a rate limit, retries later.
    """
    aioclient_mock.post(OAUTH_TOKEN_URL, status=status, json={"error": "invalid_grant"})
    entry = oauth_entry(expires_in=-10)
    await _setup_failing(hass, entry)
    assert entry.state is state
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert bool(flows) is reauth
    if reauth:
        assert flows[0]["step_id"] == "reauth_oauth"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, RunstenAuthError),
        (401, RunstenAuthError),
        (408, RunstenConnectionError),
        (429, RunstenConnectionError),
        (503, RunstenConnectionError),
    ],
)
async def test_renewal_errors(
    hass: HomeAssistant, status: int, error: type[Exception]
) -> None:
    """The integration's own reading of a renewal's status, whatever Home Assistant's
    helper does first (recent versions start the reauth of a 408 themselves): only a
    refusal asks to sign in again, not a timeout or a rate limit.
    """
    async_register_implementation(hass, DOMAIN, RunstenImplementation(hass))
    entry = oauth_entry(expires_in=-10)
    entry.add_to_hass(hass)
    failure = aiohttp.ClientResponseError(Mock(), (), status=status)
    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session"
        ".async_ensure_token_valid",
        side_effect=failure,
    ):
        token = await _async_token_source(hass, entry)
        with pytest.raises(error):
            await token()


async def test_access_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Runsten refusing a valid access token (revoked meanwhile) asks to sign in again."""
    aioclient_mock.get(HOSTED + "states", status=401)
    entry = oauth_entry()
    await _setup_failing(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows[0]["step_id"] == "reauth_oauth"


@pytest.mark.parametrize(
    ("account_id", "reason"),
    [(ACCOUNT_ID, "reauth_successful"), ("another", "wrong_account")],
)
async def test_reauth(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    account_id: str,
    reason: str,
) -> None:
    """Signing in again renews the entry's tokens, with the same account only."""
    mock_hosted(aioclient_mock)
    entry = oauth_entry()
    await setup(hass, entry)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_oauth"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.EXTERNAL_STEP

    aioclient_mock.clear_requests()
    aioclient_mock.get(HOSTED + "account", json={**account(), "account_id": account_id})
    result = await _sign_in(hass, hass_client_no_auth, aioclient_mock, result)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason
    renewed = reason == "reauth_successful"
    assert (entry.data["token"]["access_token"] == "rso_new") is renewed
    assert entry.data[CONF_URL] == URL


async def test_sign_in_cannot_read_account(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Runsten not answering once signed in: no entry, a reason told."""
    aioclient_mock.get(HOSTED + "account", status=500)
    result = await _sign_in(
        hass, hass_client_no_auth, aioclient_mock, await _start_oauth(hass)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


def test_time() -> None:
    """The fixtures' expiries are relative to now."""
    assert oauth_entry(expires_in=-10).data["token"]["expires_at"] < time.time()
