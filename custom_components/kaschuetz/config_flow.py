import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN

DATA_SCHEMA = vol.Schema({
    vol.Required("host"): cv.string,
})

class KaschuetzConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kaschütz Ofensteuerung."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="Kaschütz Ofensteuerung", data=user_input)

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)