"""Signing in with Runsten: Home Assistant's OAuth 2 with PKCE, against my.runsten.app.

The client is public (no secret): its client_id is the URL of its metadata document,
which registers My Home Assistant's address as its only redirection, whatever the
instance's own address. Every request names the integration's API as the resource,
which the access tokens then read only.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import (
    MY_AUTH_CALLBACK_PATH,
    LocalOAuth2ImplementationWithPkce,
)

from .const import (
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_RESOURCE,
    OAUTH_TOKEN_URL,
)


class RunstenImplementation(LocalOAuth2ImplementationWithPkce):
    """The authorization server of my.runsten.app, through My Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Sign in to my.runsten.app as the integration's public client."""
        super().__init__(
            hass, DOMAIN, OAUTH_CLIENT_ID, OAUTH_AUTHORIZE_URL, OAUTH_TOKEN_URL
        )

    @property
    def name(self) -> str:
        """Name the implementation."""
        return "Runsten"

    @property
    def redirect_uri(self) -> str:
        """My Home Assistant's address, the only one the client registers."""
        return MY_AUTH_CALLBACK_PATH

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Ask for a token of the integration's API, with PKCE."""
        return {**super().extra_authorize_data, "resource": OAUTH_RESOURCE}

    @property
    def extra_token_resolve_data(self) -> dict[str, Any]:
        """Exchange the code for a token of the integration's API, with PKCE."""
        return {**super().extra_token_resolve_data, "resource": OAUTH_RESOURCE}
