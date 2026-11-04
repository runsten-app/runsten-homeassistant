"""The Runsten integration: every vehicle of a Runsten account, whatever its brand."""

from __future__ import annotations

from homeassistant.const import CONF_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api import RunstenClient
from .const import CONF_HOSTED, DOMAIN, ISSUE_FREE
from .coordinator import RunstenConfigEntry, RunstenCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: RunstenConfigEntry) -> bool:
    """Read the account, then add its vehicles' entities."""
    client = RunstenClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        hosted=entry.data[CONF_HOSTED],
    )
    coordinator = RunstenCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


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
