"""Configure local records with a barcode and display name only."""
import re
import voluptuous as vol
from homeassistant import config_entries
from . import DOMAIN, CONF_ATHLETE_ID, CONF_RUNNER_NAME


class Parkrun5kConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """No credentials or remote barcode validation are required."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            barcode = str(user_input[CONF_ATHLETE_ID]).strip().upper().removeprefix("A")
            name = str(user_input[CONF_RUNNER_NAME]).strip()
            if not re.fullmatch(r"[0-9]+", barcode):
                errors[CONF_ATHLETE_ID] = "invalid_barcode"
            elif not name or len(name) > 200:
                errors[CONF_RUNNER_NAME] = "invalid_name"
            else:
                await self.async_set_unique_id(barcode)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Parkrun5k {name}", data={
                    CONF_ATHLETE_ID: barcode, CONF_RUNNER_NAME: name})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_ATHLETE_ID): str,
            vol.Required(CONF_RUNNER_NAME): str}), errors=errors)

    async def async_step_import(self, import_info):
        return await self.async_step_user(import_info)
