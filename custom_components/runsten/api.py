"""The client of Runsten's API.

The hosted offer (my.runsten.app) serves the integration under its own prefix: the
account's offer, the vehicles, and every vehicle's state in one request. Any other
instance is read through the core's JSON API, /api/v1, the same documents vehicle by
vehicle. Both take a personal access token (rst_…) as a bearer token; the hosted offer
also takes the access token of a sign-in with Runsten (OAuth), which the client asks
for before each request, renewed when it expires.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_util

HOSTED_PREFIX = "/api/cloud/homeassistant/"
CORE_PREFIX = "/api/v1/"

TOKEN_PREFIX = "rst_"

TIMEOUT = aiohttp.ClientTimeout(total=30)

# A source of access tokens: a sign-in's, valid when returned. It raises RunstenError
# when it cannot get one.
type TokenSource = Callable[[], Awaitable[str]]


class RunstenError(Exception):
    """Runsten did not answer as expected."""


class RunstenConnectionError(RunstenError):
    """Runsten could not be reached, or failed."""


class RunstenAuthError(RunstenError):
    """Runsten refused the token, or its renewal: invalid, expired or revoked."""


class RunstenNotFoundError(RunstenError):
    """No such route or vehicle."""


class RunstenRateLimitedError(RunstenError):
    """Too many requests with the token."""

    def __init__(self, retry_after: float | None) -> None:
        """Keep how long to wait, in seconds, when Runsten tells it."""
        super().__init__("rate limited")
        self.retry_after = retry_after


@dataclass(frozen=True)
class Account:
    """The hosted account's offer."""

    account_id: str | None  # tells one account from another
    plan: str  # free or plus
    plus_until: datetime | None
    read_every_s: int  # how often its values change at best
    offer_url: str

    @property
    def free(self) -> bool:
        """Whether the account is on Free."""
        return self.plan == "free"


class RunstenClient:
    """Reads one account of one instance."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        token: str | TokenSource,
        *,
        hosted: bool,
    ) -> None:
        """Read the instance at url with the token, through the hosted API or the core's."""
        self._session = session
        self._url = url.rstrip("/")
        self._token = token
        self.hosted = hosted

    async def account(self) -> Account | None:
        """Return the account's offer; None on an instance other than the hosted offer."""
        if not self.hosted:
            return None
        data = await self._get(HOSTED_PREFIX + "account")
        until = data.get("plus_until")
        return Account(
            account_id=data.get("account_id"),
            plan=data["plan"],
            plus_until=dt_util.parse_datetime(until) if until else None,
            read_every_s=int(data["read_every_s"]),
            offer_url=data["offer_url"],
        )

    async def vehicles(self) -> list[dict[str, Any]]:
        """Return the account's vehicles (the core's Vehicle)."""
        data = await self._get(self._prefix + "vehicles")
        return data["items"]

    async def states(self) -> list[dict[str, Any]]:
        """Return every vehicle's current state (the core's State).

        One request on the hosted offer; on another instance, the vehicles then each
        one's state. A vehicle deleted meanwhile is left out.
        """
        if self.hosted:
            data = await self._get(HOSTED_PREFIX + "states")
            return data["items"]
        vehicles = await self.vehicles()

        async def state(vehicle_id: str) -> dict[str, Any] | None:
            try:
                return await self._get(f"{CORE_PREFIX}vehicles/{vehicle_id}/state")
            except RunstenNotFoundError:
                return None

        states = await asyncio.gather(*(state(v["id"]) for v in vehicles))
        return [s for s in states if s is not None]

    @property
    def _prefix(self) -> str:
        return HOSTED_PREFIX if self.hosted else CORE_PREFIX

    async def _get(self, path: str) -> Any:
        token = self._token if isinstance(self._token, str) else await self._token()
        try:
            async with self._session.get(
                self._url + path,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as resp:
                if resp.status == 401:
                    raise RunstenAuthError
                if resp.status == 404:
                    raise RunstenNotFoundError(path)
                if resp.status == 429:
                    raise RunstenRateLimitedError(_retry_after(resp))
                if resp.status != 200:
                    raise RunstenConnectionError(f"HTTP {resp.status} on {path}")
                try:
                    return await resp.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise RunstenConnectionError(f"not JSON on {path}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise RunstenConnectionError(str(err) or type(err).__name__) from err


def _retry_after(resp: aiohttp.ClientResponse) -> float | None:
    try:
        return float(resp.headers["Retry-After"])
    except (KeyError, ValueError):
        return None


async def async_detect(
    session: aiohttp.ClientSession, url: str, token: str
) -> RunstenClient:
    """Return a client of the instance at url, after reading it with the token.

    The hosted offer answers its own prefix; an instance that does not know it (404) is
    read through the core's API. Raises RunstenAuthError when the token is refused,
    RunstenConnectionError when neither answers.
    """
    hosted = RunstenClient(session, url, token, hosted=True)
    try:
        await hosted.account()
    except RunstenNotFoundError:
        pass
    else:
        return hosted
    core = RunstenClient(session, url, token, hosted=False)
    try:
        await core.vehicles()
    except RunstenNotFoundError as err:
        raise RunstenConnectionError("not a Runsten instance") from err
    return core
