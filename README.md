# Runsten for Home Assistant

Every car [Runsten](https://runsten.app) reads (Volvo, Polestar, Tesla…) in Home Assistant, with
the same entities whatever the brand: battery, range, charge, odometer, doors, windows, lock,
temperatures and position.

The integration reads your account on [my.runsten.app](https://my.runsten.app), Runsten's hosted
offer, once a minute: nothing to expose from your network, no MQTT broker. It reads Runsten's
database, never your car's API, so it does not count against your car's quotas.

## Install

Requires Home Assistant 2025.8 or later (tested with 2026.10).

- **Marketplace (Home Assistant 2026.11 and later) or HACS**: add this repository as a custom
  repository of type *Integration*, then install **Runsten** and restart Home Assistant.
- **By hand**: copy `custom_components/runsten` into your configuration's `custom_components`
  folder, then restart Home Assistant.

## Connect

In Home Assistant: **Settings → Devices & services → Add integration → Runsten**, then
**Sign in with Runsten**. Runsten opens in your browser: sign in, check what Home Assistant will
read, and allow it. You come back to Home Assistant through
[My Home Assistant](https://my.home-assistant.io), which asks once for your instance's address.

Home Assistant then appears in Runsten under **Settings → Connected apps**, where you can
disconnect it: Home Assistant then asks you to sign in again. It stays connected as long as it
reads your account at least once every 30 days.

### With an access token

Choose **Use an access token** instead:

1. In Runsten: **Settings → API access → New access token**. Copy the token (it starts with
   `rst_`). It only reads your data; you can revoke it there at any time.
2. In Home Assistant, paste the token.

Each vehicle becomes a device, named as in Runsten (never by its VIN).

### Free and Plus

The integration works with every offer. On Free, Runsten reads your vehicles once an hour, so
their values change here only once an hour: a repair says so, which you can ignore. Plus reads
them in real time (every minute while driving or charging).

### A self-hosted Runsten

Choose **Use an access token**, open **Advanced settings** in the form and replace `https://my.runsten.app` with your instance's
address, then paste a token of that instance. The integration reads the instance's API,
`/api/v1`, with the same entities; there is no offer and no repair.

## Entities

| Entity | Type | Notes |
|---|---|---|
| Battery, Range, Charge limit, Odometer | sensor | %, km |
| Charging status | sensor | idle, charging, done, scheduled, discharging, error |
| Charge type | sensor | AC, DC, none |
| Charging power | sensor | kW |
| Last read | sensor | diagnostic: Runsten's latest reading of the vehicle |
| Plug, Charging, Engine | binary sensor | |
| Credential | binary sensor | a problem when the vehicle's credential (Polestar, Tesla) is refused or removed |
| Outside temperature, Cabin temperature | sensor | for a vehicle that tells them (Tesla) |
| Climate, Preconditioning, Battery heater | binary sensor | for a vehicle that tells them (Tesla) |
| Lock, doors, hood, tailgate, tank lid, windows, sunroof, Sentry Mode | binary sensor | each one the vehicle tells |
| Doors last read | sensor | diagnostic |
| Location | device tracker | can be turned off in the integration's options |

A value Runsten does not know is `unknown`, never zero. While Runsten does not answer, the
entities are unavailable.

### With Runsten's MQTT too

Runsten can also publish to an MQTT broker with Home Assistant's discovery. Both give the same
vehicles as two separate devices: keep only one of them.

## Privacy

Your vehicles' data, their position included, go from Runsten to your Home Assistant only. Turn
the position off in the integration's options (**Configure**) to remove the trackers.

## Development

```sh
uv venv -p 3.14 .venv
uv pip install -p .venv -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Licence

Apache-2.0, see [LICENSE](LICENSE).
