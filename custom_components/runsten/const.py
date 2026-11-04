"""Constants of the Runsten integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "runsten"

# The hosted offer, which the integration connects to unless told another instance.
DEFAULT_URL: Final = "https://my.runsten.app"

# The configuration entry's data: the instance's URL, the token, and whether the
# instance is the hosted offer (its own API, detected when the entry is made) or a
# self-hosted one (the core's API).
CONF_HOSTED: Final = "hosted"
SECTION_ADVANCED: Final = "advanced"

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
