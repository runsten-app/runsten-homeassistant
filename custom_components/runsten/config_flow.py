"""The configuration flow: a personal access token of my.runsten.app, or of another instance.

The URL defaults to the hosted offer; the advanced settings take a self-hosted
instance's. Signing in with Runsten (OAuth) is to come: a step of its own beside the
token's, in a menu, creating an entry of the same instance URL with its own credential.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from yarl import URL

try:  # Home Assistant 2026.10 replaced voluptuous with probatio, its drop-in.
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    TOKEN_PREFIX,
    RunstenAuthError,
    RunstenClient,
    RunstenError,
    async_detect,
)
from .const import (
    CONF_HOSTED,
    CONF_TRACK_LOCATION,
    DEFAULT_TRACK_LOCATION,
    DEFAULT_URL,
    DOMAIN,
    SECTION_ADVANCED,
)
from .coordinator import RunstenConfigEntry

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
        vol.Required(SECTION_ADVANCED): section(
            vol.Schema(
                {
                    vol.Required(CONF_URL, default=DEFAULT_URL): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.URL)
                    ),
                }
            ),
            {"collapsed": True},
        ),
    }
)

REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR})


def normalize_url(url: str) -> str | None:
    """Return the instance's URL, https unless told, without a trailing slash; None when invalid."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        parsed = URL(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.host:
        return None
    return str(parsed.with_query(None).with_fragment(None)).rstrip("/")


class RunstenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect an account of Runsten."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the token, and under the advanced settings the instance's URL."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            url = normalize_url(user_input[SECTION_ADVANCED][CONF_URL])
            if url is None:
                errors["base"] = "invalid_url"
            else:
                self._async_abort_entries_match({CONF_URL: url, CONF_TOKEN: token})
                client = await self._async_check(url, token, errors)
                if client is not None:
                    return self.async_create_entry(
                        title=URL(url).host or url,
                        data={
                            CONF_URL: url,
                            CONF_TOKEN: token,
                            CONF_HOSTED: client.hosted,
                        },
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
            description_placeholders={"default_url": DEFAULT_URL},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Runsten refused the token: ask for another."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token of the same instance."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            client = await self._async_check(entry.data[CONF_URL], token, errors)
            if client is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token, CONF_HOSTED: client.hosted}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )

    async def _async_check(
        self, url: str, token: str, errors: dict[str, str]
    ) -> RunstenClient | None:
        """Read the instance with the token; the client, or None with the error set."""
        if not token.startswith(TOKEN_PREFIX):
            errors[CONF_TOKEN] = "invalid_token"
            return None
        try:
            return await async_detect(async_get_clientsession(self.hass), url, token)
        except RunstenAuthError:
            errors["base"] = "invalid_auth"
        except RunstenError:
            errors["base"] = "cannot_connect"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: RunstenConfigEntry) -> OptionsFlow:
        """Return the options' flow: whether to track the vehicles' position."""
        return RunstenOptionsFlow()


class RunstenOptionsFlow(OptionsFlowWithReload):
    """Whether to publish each vehicle's position as a device tracker; reloads the entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRACK_LOCATION,
                        default=self.config_entry.options.get(
                            CONF_TRACK_LOCATION, DEFAULT_TRACK_LOCATION
                        ),
                    ): bool,
                }
            ),
        )
