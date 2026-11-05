"""The Runsten integration: every vehicle of a Runsten account, whatever its brand."""

from __future__ import annotations

import aiohttp
from homeassistant.const import CONF_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_entry_oauth2_flow,
    config_validation as cv,
    issue_registry as ir,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from .api import RunstenAuthError, RunstenClient, RunstenConnectionError, TokenSource
from .const import CONF_HOSTED, DOMAIN, ISSUE_FREE
from .coordinator import RunstenConfigEntry, RunstenCoordinator
from .oauth import RunstenImplementation

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Offer signing in with Runsten, and renew the tokens of the entries that did."""
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN, RunstenImplementation(hass)
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RunstenConfigEntry) -> bool:
    """Read the account, then add its vehicles' entities."""
    token: str | TokenSource
    if "auth_implementation" in entry.data:
        token = await _async_token_source(hass, entry)
    else:
        token = entry.data[CONF_TOKEN]
    client = RunstenClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        token,
        hosted=entry.data[CONF_HOSTED],
    )
    coordinator = RunstenCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_token_source(
    hass: HomeAssistant, entry: RunstenConfigEntry
) -> TokenSource:
    """Return the access token of the entry's sign-in, renewed when it expires.

    Runsten refusing the renewal (the grant revoked, or unused for 30 days) is an
    authentication error, which asks the user to sign in again; any other failure is
    Runsten not answering, a request timed out or limited (408, 429) among them.
    """
    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    async def token() -> str:
        try:
            await session.async_ensure_token_valid()
        except aiohttp.ClientResponseError as err:
            # A 408 reaches here as a plain error (RunstenImplementation), never
            # Home Assistant's refusal, which would start the reauth.
            if 400 <= err.status < 500 and err.status not in (408, 429):
                raise RunstenAuthError from err
            raise RunstenConnectionError(f"token renewal: HTTP {err.status}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise RunstenConnectionError(str(err) or type(err).__name__) from err
        return session.token["access_token"]

    return token


async def async_unload_entry(hass: HomeAssistant, entry: RunstenConfigEntry) -> bool:
    """Remove the entities."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RunstenConfigEntry) -> None:
    """Remove the repair of a Free account with its entry."""
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_FREE}_{entry.entry_id}")


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: RunstenConfigEntry, device: DeviceEntry
) -> bool:
    """Let the user remove a vehicle's device only once the account no longer has it."""
    vehicles = entry.runtime_data.data.vehicles
    return not any(d == DOMAIN and i in vehicles for d, i in device.identifiers)
