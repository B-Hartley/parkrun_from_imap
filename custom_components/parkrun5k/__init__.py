"""Local parkrun records, populated only by email imports or manual actions."""
from __future__ import annotations

import asyncio
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .email_import import parse_email, merge_email
from .local_data import get_event_name, prepare_saved_data
from .records import manual_update, structured_update, refresh_locations, MANUAL_FIELDS, parse_results_html, merge_results_html

DOMAIN = "parkrun5k"
CONF_ATHLETE_ID = "athlete_id"
CONF_RUNNER_NAME = "runner_name"
PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Restore local records without validating against or contacting a server."""
    coordinator = ParkrunDataUpdateCoordinator(hass, entry)
    cached = await coordinator.store.async_load()
    data = prepare_saved_data(cached, coordinator.runner_name)
    if cached is not None and data != cached:
        await coordinator.store.async_save(data)
    coordinator.async_set_updated_data(data)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register once; resolve live coordinators on every call (supports reloads).
    if not hass.services.has_service(DOMAIN, "import_email"):
        async def handle_import_email(call):
            barcode = str(call.data[CONF_ATHLETE_ID]).upper().removeprefix("A")
            coordinators = [c for c in hass.data[DOMAIN].values()
                            if isinstance(c, ParkrunDataUpdateCoordinator)
                            and str(c.barcode) == barcode]
            if len(coordinators) != 1:
                raise ServiceValidationError("Select exactly one configured parkrun runner")
            try:
                run = parse_email(call.data["subject"], call.data["body"], barcode)
            except (ValueError, TypeError) as err:
                raise ServiceValidationError(str(err)) from err
            target = coordinators[0]
            async with target.import_lock:
                data = merge_email(target.data, run, target.runner_name, get_event_name)
                await target.store.async_save(data)
                target.async_set_updated_data(data)

        hass.services.async_register(
            DOMAIN, "import_email", handle_import_email,
            schema=vol.Schema({vol.Required(CONF_ATHLETE_ID): cv.string,
                               vol.Required("subject"): cv.string,
                               vol.Required("body"): cv.string}),
        )

    if not hass.services.has_service(DOMAIN, "import_html"):
        async def handle_import_html(call):
            barcode = str(call.data[CONF_ATHLETE_ID]).upper().removeprefix("A")
            targets = [c for c in hass.data[DOMAIN].values()
                       if isinstance(c, ParkrunDataUpdateCoordinator) and str(c.barcode) == barcode]
            if len(targets) != 1:
                raise ServiceValidationError("Select exactly one configured parkrun runner")
            try:
                runs = parse_results_html(call.data["html"], barcode)
            except (ValueError, TypeError) as err:
                raise ServiceValidationError(str(err)) from err
            target = targets[0]
            async with target.import_lock:
                data = merge_results_html(target.data, runs, target.runner_name, get_event_name)
                await target.store.async_save(data)
                target.async_set_updated_data(data)

        hass.services.async_register(
            DOMAIN, "import_html", handle_import_html,
            schema=vol.Schema({vol.Required(CONF_ATHLETE_ID): cv.string,
                               vol.Required("html"): cv.string}),
        )

    if not hass.services.has_service(DOMAIN, "update_data"):
        async def handle_update_data(call):
            barcode = str(call.data[CONF_ATHLETE_ID]).upper().removeprefix("A")
            targets = [c for c in hass.data[DOMAIN].values()
                       if isinstance(c, ParkrunDataUpdateCoordinator) and str(c.barcode) == barcode]
            if len(targets) != 1:
                raise ServiceValidationError("Select exactly one configured parkrun runner")
            target = targets[0]
            changes = {key: value for key, value in call.data.items() if key != CONF_ATHLETE_ID}
            async with target.import_lock:
                try:
                    if "updates" in changes:
                        if len(changes) != 1:
                            raise ValueError("Use updates or flat fields, not both")
                        data = structured_update(target.data, changes["updates"], target.runner_name,
                                                 dt_util.now().date(), get_event_name)
                    else:
                        data = manual_update(target.data, changes, target.runner_name)
                        refresh_locations(data, get_event_name)
                except (ValueError, TypeError) as err:
                    raise ServiceValidationError(str(err)) from err
                await target.store.async_save(data)
                target.async_set_updated_data(data)

        hass.services.async_register(
            DOMAIN, "update_data", handle_update_data,
            schema=vol.Schema({vol.Required(CONF_ATHLETE_ID): cv.string,
                               vol.Optional("updates"): dict,
                               **{vol.Optional(key): object for key in MANUAL_FIELDS}}),
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload sensors and unregister actions after the last runner is unloaded."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        for service in ("import_email", "import_html", "update_data"):
            hass.services.async_remove(DOMAIN, service)
    return True


class ParkrunDataUpdateCoordinator(DataUpdateCoordinator):
    """Local push coordinator: no polling, scheduled fetches or network client."""

    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.runner_name = entry.data[CONF_RUNNER_NAME]
        self.barcode = str(entry.data[CONF_ATHLETE_ID]).upper().removeprefix("A")
        self.entry_id = entry.entry_id
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.results")
        self.import_lock = asyncio.Lock()
