"""Constants of the Runsten integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "runsten"

# The hosted offer, which the integration connects to unless told another instance.
DEFAULT_URL: Final = "https://my.runsten.app"

# The configuration entry's data: the instance's URL, the token, and whether the
# instance is the hosted offer (its own API, detected when the entry is made) or a
# self-hosted one (the core's API). An entry signed in with Runsten holds Home
# Assistant's OAuth 2 data instead of the token: its implementation and its tokens.
CONF_HOSTED: Final = "hosted"
SECTION_ADVANCED: Final = "advanced"

# Signing in with Runsten: the hosted offer's authorization server (OAuth 2.1, PKCE),
# for a public client whose client_id is the URL of its metadata document, which
# names My Home Assistant as its only redirection. Its tokens read the integration's
# API only (the resource, RFC 8707).
OAUTH_CLIENT_ID: Final = "https://runsten.app/homeassistant/client.json"
OAUTH_AUTHORIZE_URL: Final = DEFAULT_URL + "/api/cloud/oauth/authorize"
OAUTH_TOKEN_URL: Final = DEFAULT_URL + "/api/cloud/oauth/token"
OAUTH_RESOURCE: Final = DEFAULT_URL + "/api/cloud/homeassistant"

# The option that publishes each vehicle's position as a device tracker.
CONF_TRACK_LOCATION: Final = "track_location"
DEFAULT_TRACK_LOCATION: Final = True

# Runsten reads a vehicle once a minute at best (while driving or charging): polling
# more often would get nothing new.
UPDATE_INTERVAL: Final = timedelta(minutes=1)
# The vehicles' details and the account's offer change rarely: read again once an hour,
# or as soon as a vehicle appears.
DETAILS_INTERVAL: Final = timedelta(hours=1)

# The repair of a Free account, which reads its vehicles once an hour.
ISSUE_FREE: Final = "free_plan"
