"""Config and options flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wakeup_alarm.const import (
    CONF_COVERS,
    CONF_MEDIA_ID,
    CONF_MEDIA_PLAYER,
    CONF_SOURCES,
    CONF_STOP_ON_CHANGE,
    DOMAIN,
)

from .common import COVER, DIMMER, PLUG, STATION, controller, setup_alarm


async def test_create_alarm(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Спальня Ульяны", CONF_SOURCES: [DIMMER, PLUG], CONF_MEDIA_PLAYER: STATION, CONF_COVERS: [COVER]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Спальня Ульяны"
    entry = result["result"]
    assert entry.options[CONF_SOURCES] == [DIMMER, PLUG]
    assert entry.options[CONF_MEDIA_ID] == "включи мою волну"
    await hass.async_block_till_done()
    assert controller(entry).settings["enabled"] is False


async def test_no_devices(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Empty"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}


async def test_duplicate_name(hass: HomeAssistant) -> None:
    await setup_alarm(hass, title="Спальня", enabled=False)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "спальня", CONF_SOURCES: [DIMMER]}
    )
    assert result["errors"] == {"name": "name_exists"}


async def test_options_keep_schedule(hass: HomeAssistant) -> None:
    entry = await setup_alarm(hass)
    controller(entry).set_setting("wake_time", "06:15:00")
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SOURCES: [PLUG],
            "media_type": "text",
            "media_id": "Доброе утро",
            "start_volume": 10,
            "cover_position": 80,
            "sun_elevation": 2,
            CONF_STOP_ON_CHANGE: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_SOURCES] == [PLUG]
    assert CONF_MEDIA_PLAYER not in entry.options
    assert entry.options["cover_position"] == 80
    ctl = controller(entry)
    assert ctl.settings["wake_time"] == "06:15:00"
    assert ctl.settings["enabled"] is True


async def test_options_require_device(hass: HomeAssistant) -> None:
    entry = await setup_alarm(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "media_type": "command",
            "media_id": "x",
            "start_volume": 5,
            "cover_position": 100,
            "sun_elevation": 0,
            CONF_STOP_ON_CHANGE: True,
        },
    )
    assert result["errors"] == {"base": "no_devices"}
