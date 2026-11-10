"""Schedule: weekdays, skip next, persistence, restarts, entities."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.wakeup_alarm.const import SET_ENABLED, SET_SKIP_NEXT, AlarmState

from .common import advance, controller, entity_id, msk, setup_alarm, setup_world


async def test_next_wake_sensor_and_weekends(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(13, 8, 0))  # Friday
    entry = await setup_alarm(hass)
    state = hass.states.get(entity_id(hass, entry, "sensor", "next_wake"))
    assert state.state == "2026-11-16T04:00:00+00:00"  # 07:00 MSK
    assert controller(entry).next_wake == msk(16, 7)
    assert hass.states.get(entity_id(hass, entry, "sensor", "status")).state == "scheduled"


async def test_disabled_alarm(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id(hass, entry, "switch", "enabled")}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, entry, "sensor", "next_wake")).state == "unknown"
    assert hass.states.get(entity_id(hass, entry, "sensor", "status")).state == "off"


async def test_entities_change_schedule(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": entity_id(hass, entry, "time", "wake_time"), "time": "08:30:00"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id(hass, entry, "switch", "weekday_mon")}, blocking=True
    )
    await hass.async_block_till_done()
    assert controller(entry).next_wake == msk(10, 8, 30)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id(hass, entry, "number", "fade_duration"), "value": 25},
        blocking=True,
    )
    assert controller(entry).settings["fade_duration"] == 25


async def test_skip_next(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 22, 0))  # Monday evening
    entry = await setup_alarm(hass)
    ctl = controller(entry)
    ctl.set_setting(SET_SKIP_NEXT, True)
    await hass.async_block_till_done()
    assert ctl.next_wake == msk(11, 7)
    await advance(hass, freezer, msk(10, 7, 0, 5), step=60)
    assert rec("light.turn_on") == []
    assert rec("media_player.play_media") == []
    assert ctl.settings[SET_SKIP_NEXT] is False
    assert ctl.next_wake == msk(11, 7)
    assert ctl.state == AlarmState.SCHEDULED


async def test_enable_late_starts_mid_sunrise(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 55))
    entry = await setup_alarm(hass)
    await hass.async_block_till_done()
    assert controller(entry).state == AlarmState.SUNRISE
    assert 100 <= rec.brightness()[0] <= 110


async def test_settings_survive_reload(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 3, 0))
    entry = await setup_alarm(hass)
    controller(entry).set_setting("max_volume", 35)
    controller(entry).set_weekday(0, False)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    ctl = controller(entry)
    assert ctl.settings[SET_ENABLED] is True
    assert ctl.settings["max_volume"] == 35
    assert ctl.settings["weekdays"][0] is False
    assert ctl.next_wake == msk(10, 7)


async def test_restart_during_sunrise_continues(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 48), step=10)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    before = len(rec.brightness())
    freezer.move_to(msk(9, 6, 52))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ctl = controller(entry)
    assert ctl.state == AlarmState.SUNRISE
    resumed = rec.brightness()[before:]
    assert resumed
    # Curve value at 7/15 of the fade: 255 * (7/15) ** 2.2 ~= 47
    assert 40 <= resumed[0] <= 55


async def test_no_rerun_after_stop_and_restart(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 48), step=10)
    controller(entry).async_stop()
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert controller(entry).state == AlarmState.SCHEDULED
    assert controller(entry).next_wake == msk(10, 7)


async def test_restart_after_wake_does_not_rerun(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 7, 0, 5), step=10)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert controller(entry).state == AlarmState.SCHEDULED
    assert controller(entry).next_wake == msk(10, 7)
