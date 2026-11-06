# AGENTS.md

The Home Assistant integration of Runsten (domain `runsten`), a custom integration published in
Home Assistant's Marketplace (HACS). Public repository, Apache-2.0. Read this before changing
anything.

## What it is

A client of Runsten's API, in Python, inside Home Assistant:

- **By default, the hosted offer** (`https://my.runsten.app`): its own routes under
  `/api/cloud/homeassistant/` (`account`, `vehicles`, `vehicles/{id}`, `vehicles/{id}/state`,
  `states`). `states` gives every vehicle in one request. Signed in with Runsten (OAuth 2 with
  PKCE, Home Assistant's `config_entry_oauth2_flow`): a public client whose `client_id` is the
  URL of its metadata document, `https://runsten.app/homeassistant/client.json`, which names My
  Home Assistant's `https://my.home-assistant.io/redirect/oauth` as its only redirection; every
  request names the resource `https://my.runsten.app/api/cloud/homeassistant`, which its tokens
  read only. The access token lasts an hour, the refresh token is renewed at each use and dies
  after 30 days unused. Or with a personal access token `rst_…`.
- **A self-hosted instance** (advanced settings of the form): the core's `/api/v1` with the same
  token, the same documents (`Vehicle`, `State`) vehicle by vehicle; no offer.
- Which one is detected when the entry is made (`api.async_detect`: the hosted route answers, or
  404) and stored in the entry (`hosted`). An entry signed in with Runsten is the hosted offer's,
  its unique ID the account's (`account_id` of `account`); one made with a token has none.

The value is on the server: nothing secret or paid lives here. The client reads only what the
hosted offer also relays, so that one code serves both.

## Layout

```
custom_components/runsten/
  api.py             the client: errors, Account, hosted or core routes, detection; a token or
                     a source of tokens
  oauth.py           signing in with Runsten: the PKCE implementation, through My Home Assistant
  coordinator.py     DataUpdateCoordinator: states every minute; vehicles and offer hourly or
                     when a vehicle appears; device names (labels), stale devices, Free's repair
  entity.py          base entity, dynamic addition of each vehicle's entities, State readers
  sensor.py, binary_sensor.py, device_tracker.py
  config_flow.py     menu: sign in with Runsten (OAuth) or the token form (URL in a collapsed
                     section); reauth of either kind; options (position)
  translations/      en, fr, nl, sv: the same keys
  icons.json, manifest.json
  brand/             the icon Home Assistant shows once installed (light and dark, 256 and
                     512 px): Runsten's mark, the core's web/public/favicon.svg
tests/               pytest-homeassistant-custom-component, the API mocked (aioclient_mock)
```

## Rules

- **The entities are MQTT discovery's** (the core's `internal/publish`): same names, device
  classes, units, and the same "told only where the vehicle tells it" for the climate and the
  openings. Unique IDs are `<vehicle id>_<key>`, distinct from MQTT's `runsten_<id>_<object>`.
- **Unknown is `None`, never a zero** or an off; unavailable while Runsten does not answer.
- **A device per vehicle**, named as the web interface does (`coordinator.label`), never by its
  VIN. The VIN is never shown, logged or stored.
- **One request a minute per account** (`states`); nothing polls faster: Runsten reads a vehicle
  once a minute at best.
- **Translations**: English, French, Dutch and Swedish together, the same keys, no URL in a string
  (hassfest refuses it: a placeholder). Runsten's offers are Free/Plus, Gratuit/Plus, Free/Plus, Gratis/Plus.
- Current Home Assistant idioms: `probatio` (imported as `vol`, voluptuous as fallback), sections
  rather than advanced mode, `OptionsFlowWithReload`, `entry.runtime_data`. The minimum version
  is `hacs.json`'s `homeassistant`.
- This repository is public: it may name `my.runsten.app` and the core's public API, never the
  private repositories, their packages or their decision records.

## Checks

```sh
uv venv -p 3.14 .venv && uv pip install -p .venv -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
docker run --rm --platform linux/amd64 -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest
```

CI runs the same (`tests.yml`) and hassfest with HACS's action (`validate.yml`).

## Releases

A GitHub release `vX.Y.Z` is what the Marketplace installs: `manifest.json`'s `version` is
`X.Y.Z` first, in its own commit. Never tag or release without the maintainer's explicit request.

## Conventions

English in code, comments, commits and issues. The issues are tracked with the rest of Runsten's,
not in this repository; no commit message names an issue. Commits only when asked, atomic; never
push, tag, amend or force-push without an explicit request.
