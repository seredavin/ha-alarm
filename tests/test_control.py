"""Stop, snooze, auto stop, stopping on lighting changes, test runs, services."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from custom_components.wakeup_alarm.const import (
    CONF_STOP_ON_CHANGE,
    DOMAIN,
    EVENT_SNOOZED,
    EVENT_STOPPED,
    SET_AUTO_STOP,
    SET_WEEKDAYS,
    AlarmState,
)

from .common import (
    DIMMER,
    PLUG,
    STATION,
    advance,
    controller,
    entity_id,
    msk,
    setup_alarm,
    setup_world,
)

DIMMABLE = {"supported_color_modes": ["brightness"]}


def stop_reasons(rec) -> list[str]:
    return [e.data["reason"] for e in rec.events if e.event_type == EVENT_STOPPED]


def echo_dimmer(hass: HomeAssistant, rec, offset: int = 0) -> None:
    """Report the last commanded brightness back, like an MQTT device would."""
    hass.states.async_set(DIMMER, "on", {**DIMMABLE, "brightness": rec.brightness()[-1] + offset})


async def ringing(hass: HomeAssistant, freezer: FrozenDateTimeFactory, **options):
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass, **options)
    await advance(hass, freezer, msk(9, 7, 0, 2), step=10)
    assert controller(entry).state == AlarmState.RINGING
    hass.states.async_set(STATION, "playing", {"volume_level": 0.5})
    await hass.async_block_till_done()
    return rec, entry


async def test_stop_button_restores_volume(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec, entry = await ringing(hass, freezer)
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id(hass, entry, "button", "stop")}, blocking=True
    )
    await hass.async_block_till_done()
    assert len(rec("media_player.media_stop", STATION)) == 1
    assert rec("media_player.volume_set")[-1].data["volume_level"] == 0.2
    assert controller(entry).state == AlarmState.SCHEDULED
    assert stop_reasons(rec) == ["button"]
    assert controller(entry).next_wake == msk(10, 7)


async def test_stop_when_idle_does_nothing(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    controller(entry).async_stop()
    await hass.async_block_till_done()
    assert stop_reasons(rec) == []
    assert controller(entry).state == AlarmState.SCHEDULED


async def test_snooze_and_resume(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec, entry = await ringing(hass, freezer)
    ctl = controller(entry)
    ctl.async_snooze()
    await hass.async_block_till_done()
    assert ctl.state == AlarmState.SNOOZED
    assert len(rec("media_player.media_pause", STATION)) == 1
    assert EVENT_SNOOZED in rec.event_types()
    hass.states.async_set(STATION, "paused", {"volume_level": 0.5})
    plays = len(rec("media_player.play_media"))

    await advance(hass, freezer, msk(9, 7, 8, 58), step=30)
    assert ctl.state == AlarmState.SNOOZED
    await advance(hass, freezer, msk(9, 7, 9, 4))
    assert ctl.state == AlarmState.RINGING
    assert len(rec("media_player.play_media")) == plays + 1
    assert rec("media_player.volume_set")[-1].data["volume_level"] == 0.5
    assert stop_reasons(rec) == []


async def test_auto_stop(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec, entry = await ringing(hass, freezer)
    await advance(hass, freezer, msk(9, 7, 29, 50), step=30)
    assert controller(entry).state == AlarmState.RINGING
    await advance(hass, freezer, msk(9, 7, 30, 5))
    assert controller(entry).state == AlarmState.SCHEDULED
    assert stop_reasons(rec) == ["auto"]
    assert rec("media_player.volume_set")[-1].data["volume_level"] == 0.2


async def test_auto_stop_disabled(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    controller(entry).set_setting(SET_AUTO_STOP, 0)
    await advance(hass, freezer, msk(9, 8, 0), step=30)
    assert controller(entry).state == AlarmState.RINGING


async def test_light_switched_off_stops(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 50), step=10)
    echo_dimmer(hass, rec)
    await advance(hass, freezer, msk(9, 6, 50, 10))
    hass.states.async_set(DIMMER, "off", DIMMABLE)
    await hass.async_block_till_done()
    assert stop_reasons(rec) == ["manual"]
    assert controller(entry).state == AlarmState.SCHEDULED
    calls = len(rec("light.turn_on"))
    await advance(hass, freezer, msk(9, 7, 1), step=10)
    assert len(rec("light.turn_on")) == calls
    assert rec("media_player.play_media") == []
    assert rec("switch.turn_on") == []


async def test_plug_switched_on_early_stops(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 50), step=10)
    hass.states.async_set(PLUG, "on")
    await hass.async_block_till_done()
    assert stop_reasons(rec) == ["manual"]


async def test_dimmer_switched_on_before_fade_stops(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    controller(entry).set_setting("fade_duration", 5)  # covers start the run at 06:45, light at 06:55
    await advance(hass, freezer, msk(9, 6, 50), step=10)
    assert controller(entry).state == AlarmState.SUNRISE
    assert rec.brightness() == []
    hass.states.async_set(DIMMER, "on", {**DIMMABLE, "brightness": 120})
    await hass.async_block_till_done()
    assert stop_reasons(rec) == ["manual"]


async def test_brightness_changed_by_hand_stops(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 52), step=10)
    echo_dimmer(hass, rec)
    await hass.async_block_till_done()
    assert stop_reasons(rec) == []
    hass.states.async_set(DIMMER, "on", {**DIMMABLE, "brightness": 200})
    await hass.async_block_till_done()
    assert stop_reasons(rec) == ["manual"]


async def test_device_echo_is_not_a_change(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 45, 1))
    # Right after the first switch-on the device briefly reports a stale "off"
    echo_dimmer(hass, rec)
    hass.states.async_set(DIMMER, "off", DIMMABLE)
    await hass.async_block_till_done()
    echo_dimmer(hass, rec)
    for minute in range(46, 60):
        await advance(hass, freezer, msk(9, 6, minute, 30), step=5)
        echo_dimmer(hass, rec, offset=-2)  # device rounds a little
        await hass.async_block_till_done()
    assert stop_reasons(rec) == []
    assert controller(entry).state == AlarmState.SUNRISE


async def test_unavailable_is_not_a_change(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 50), step=10)
    echo_dimmer(hass, rec)
    await advance(hass, freezer, msk(9, 6, 50, 10))
    hass.states.async_set(DIMMER, "unavailable")
    await hass.async_block_till_done()
    echo_dimmer(hass, rec)
    await hass.async_block_till_done()
    assert stop_reasons(rec) == []


async def test_light_off_after_wake_stops_speaker(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec, _entry = await ringing(hass, freezer)
    hass.states.async_set(DIMMER, "on", {**DIMMABLE, "brightness": 255})
    await advance(hass, freezer, msk(9, 7, 0, 30))
    hass.states.async_set(DIMMER, "off", DIMMABLE)
    await hass.async_block_till_done()
    assert stop_reasons(rec) == ["manual"]
    assert len(rec("media_player.media_stop")) == 1
    assert rec("media_player.volume_set")[-1].data["volume_level"] == 0.2


async def test_speaker_stopped_by_voice_stops(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass, media_lead=0)
    controller(entry).set_setting("media_lead", 5)
    await advance(hass, freezer, msk(9, 6, 55, 5), step=10)
    hass.states.async_set(STATION, "playing", {"volume_level": 0.1})
    await advance(hass, freezer, msk(9, 6, 55, 30))
    hass.states.async_set(STATION, "idle", {"volume_level": 0.1})
    await advance(hass, freezer, msk(9, 6, 55, 33))
    assert stop_reasons(rec) == []  # debounce
    await advance(hass, freezer, msk(9, 6, 55, 37))
    assert stop_reasons(rec) == ["manual"]


async def test_speaker_short_glitch_is_ignored(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 58, 5), step=10)
    hass.states.async_set(STATION, "playing", {"volume_level": 0.1})
    await advance(hass, freezer, msk(9, 6, 58, 30))
    hass.states.async_set(STATION, "idle", {"volume_level": 0.1})
    await advance(hass, freezer, msk(9, 6, 58, 32))
    hass.states.async_set(STATION, "playing", {"volume_level": 0.1})
    await advance(hass, freezer, msk(9, 6, 58, 45))
    assert stop_reasons(rec) == []


async def test_option_off_keeps_going(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass, **{CONF_STOP_ON_CHANGE: False})
    await advance(hass, freezer, msk(9, 6, 50), step=10)
    echo_dimmer(hass, rec)
    await advance(hass, freezer, msk(9, 6, 50, 10))
    hass.states.async_set(DIMMER, "off", DIMMABLE)
    calls = len(rec("light.turn_on"))
    await advance(hass, freezer, msk(9, 6, 51), step=5)
    assert stop_reasons(rec) == []
    assert controller(entry).state == AlarmState.SUNRISE
    assert len(rec("light.turn_on")) > calls


async def test_one_shot_switches_off_after_stop(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    ctl = controller(entry)
    ctl.set_setting(SET_WEEKDAYS, [False] * 7)
    await advance(hass, freezer, msk(9, 7, 0, 5), step=10)
    ctl.async_stop()
    await hass.async_block_till_done()
    assert ctl.settings["enabled"] is False
    assert ctl.state == AlarmState.OFF
    assert ctl.next_wake is None


async def test_trigger_service_compresses_sequence(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 12, 0))
    entry = await setup_alarm(hass, enabled=False)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    await hass.services.async_call(DOMAIN, "trigger", {"device_id": device.id, "duration": 60}, blocking=True)
    await hass.async_block_till_done()
    ctl = controller(entry)
    assert ctl.state == AlarmState.SUNRISE
    start = dt_util.now()
    await advance(hass, freezer, start + timedelta(seconds=50))
    assert rec("media_player.play_media") == []
    await advance(hass, freezer, start + timedelta(seconds=55))
    assert len(rec("media_player.play_media")) == 1
    assert rec("switch.turn_on") == []
    await advance(hass, freezer, start + timedelta(seconds=61))
    assert ctl.state == AlarmState.RINGING
    assert rec.brightness()[-1] == 255
    assert len(rec("switch.turn_on", PLUG)) == 1
    assert len(rec("cover.set_cover_position")) == 1
    # The test run does not touch the schedule
    assert ctl.settings["enabled"] is False
    assert ctl.next_wake is None


async def test_stop_service_targets_one_alarm(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    first = await setup_alarm(hass, title="First")
    second = await setup_alarm(hass, title="Second")
    await advance(hass, freezer, msk(9, 6, 50), step=10)
    await hass.services.async_call(
        DOMAIN, "stop", {"entity_id": entity_id(hass, first, "sensor", "status")}, blocking=True
    )
    await hass.async_block_till_done()
    assert controller(first).state == AlarmState.SCHEDULED
    assert controller(second).state == AlarmState.SUNRISE
    assert [e.data["name"] for e in rec.events if e.event_type == EVENT_STOPPED] == ["First"]


async def test_next_day_replaces_ringing_run(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    controller(entry).set_setting(SET_AUTO_STOP, 0)
    await advance(hass, freezer, msk(9, 7, 0, 5), step=10)
    assert controller(entry).state == AlarmState.RINGING
    freezer.move_to(msk(10, 6, 44, 50))
    await advance(hass, freezer, msk(10, 6, 45, 5), step=5)
    assert controller(entry).state == AlarmState.SUNRISE
    assert controller(entry).run.wake_at == msk(10, 7)
    assert stop_reasons(rec) == []


async def test_disable_during_sunrise_stops(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 59), step=10)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id(hass, entry, "switch", "enabled")}, blocking=True
    )
    await hass.async_block_till_done()
    assert stop_reasons(rec) == ["disabled"]
    assert controller(entry).state == AlarmState.OFF
    assert rec("media_player.volume_set")[-1].data["volume_level"] == 0.2
