"""Config and options flow for the Wake-up Alarm integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    CONF_COVER_POSITION,
    CONF_COVERS,
    CONF_MEDIA_ID,
    CONF_MEDIA_PLAYER,
    CONF_MEDIA_TYPE,
    CONF_SOURCES,
    CONF_START_VOLUME,
    CONF_STOP_ON_CHANGE,
    CONF_SUN_ELEVATION,
    CONF_WEATHER,
    DEFAULT_COVER_POSITION,
    DEFAULT_MEDIA_TYPE,
    DEFAULT_START_VOLUME,
    DEFAULT_STOP_ON_CHANGE,
    DEFAULT_SUN_ELEVATION,
    DOMAIN,
)

DEFAULT_OPTIONS: dict[str, Any] = {
    CONF_SOURCES: [],
    CONF_COVERS: [],
    CONF_MEDIA_TYPE: DEFAULT_MEDIA_TYPE,
    CONF_START_VOLUME: DEFAULT_START_VOLUME,
    CONF_COVER_POSITION: DEFAULT_COVER_POSITION,
    CONF_SUN_ELEVATION: DEFAULT_SUN_ELEVATION,
    CONF_STOP_ON_CHANGE: DEFAULT_STOP_ON_CHANGE,
}

DEVICE_FIELDS: dict[Any, Any] = {
    vol.Optional(CONF_SOURCES): selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["light", "switch"], multiple=True)
    ),
    vol.Optional(CONF_MEDIA_PLAYER): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
    vol.Optional(CONF_COVERS): selector.EntitySelector(selector.EntitySelectorConfig(domain="cover", multiple=True)),
}

BEHAVIOUR_FIELDS: dict[Any, Any] = {
    vol.Required(CONF_MEDIA_TYPE): selector.TextSelector(),
    vol.Required(CONF_START_VOLUME): selector.NumberSelector(
        selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%")
    ),
    vol.Required(CONF_COVER_POSITION): selector.NumberSelector(
        selector.NumberSelectorConfig(min=1, max=100, step=1, unit_of_measurement="%")
    ),
    vol.Required(CONF_SUN_ELEVATION): selector.NumberSelector(
        selector.NumberSelectorConfig(min=-18, max=30, step=0.5, unit_of_measurement="°")
    ),
    vol.Required(CONF_STOP_ON_CHANGE): selector.BooleanSelector(),
}


def _has_devices(data: dict[str, Any]) -> bool:
    return bool(data.get(CONF_SOURCES) or data.get(CONF_MEDIA_PLAYER) or data.get(CONF_COVERS))


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize optional device fields cleared in the form."""
    data = dict(data)
    data[CONF_SOURCES] = list(data.get(CONF_SOURCES) or [])
    data[CONF_COVERS] = list(data.get(CONF_COVERS) or [])
    for key in (CONF_MEDIA_PLAYER, CONF_WEATHER):
        if not data.get(key):
            data.pop(key, None)
    for key in (CONF_START_VOLUME, CONF_COVER_POSITION):
        if key in data:
            data[key] = int(data[key])
    return data


class WakeupAlarmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create an alarm."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the alarm name and devices."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if any(entry.title.casefold() == name.casefold() for entry in self._async_current_entries()):
                errors[CONF_NAME] = "name_exists"
            elif not _has_devices(user_input):
                errors["base"] = "no_devices"
            else:
                devices = {key: value for key, value in user_input.items() if key != CONF_NAME}
                return self.async_create_entry(title=name, data={}, options=_clean({**DEFAULT_OPTIONS, **devices}))

        schema = vol.Schema({vol.Required(CONF_NAME): selector.TextSelector(), **DEVICE_FIELDS})
        suggested = user_input or {}
        if user_input is None and (weather := sorted(self.hass.states.async_entity_ids("weather"))):
            suggested = {CONF_WEATHER: weather[0]}
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return WakeupAlarmOptionsFlow()


class WakeupAlarmOptionsFlow(OptionsFlow):
    """Change alarm devices and behaviour."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if _has_devices(user_input):
                data = _clean(user_input)
                if CONF_MEDIA_ID in self.config_entry.options:
                    data[CONF_MEDIA_ID] = self.config_entry.options[CONF_MEDIA_ID]  # kept for rollback to 0.2.x
                return self.async_create_entry(data=data)
            errors["base"] = "no_devices"

        schema = vol.Schema({**DEVICE_FIELDS, **BEHAVIOUR_FIELDS})
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or current),
            errors=errors,
        )
