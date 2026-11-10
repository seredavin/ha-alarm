"""Wake-up sequence: lights, speaker, covers."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.wakeup_alarm.const import (
    EVENT_RINGING,
    EVENT_SUNRISE_STARTED,
    SET_FADE,
    SET_MEDIA_LEAD,
    AlarmState,
)

from .common import (
    COVER,
    DIMMER,
    ONOFF_LIGHT,
    PLUG,
    STATION,
    advance,
    controller,
    entity_id,
    msk,
    setup_alarm,
    setup_world,
)


async def test_full_sequence(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    ctl = controller(entry)
    assert ctl.state == AlarmState.SCHEDULED
    assert ctl.next_wake == msk(9, 7)

    await advance(hass, freezer, msk(9, 6, 44, 58), step=60)
    assert rec("light.turn_on") == []

    await advance(hass, freezer, msk(9, 6, 45, 2))
    assert ctl.state == AlarmState.SUNRISE
    assert rec.brightness() == [1]
    assert EVENT_SUNRISE_STARTED in rec.event_types()
    # Summer: sun is up, covers open at the start of their window
    assert [c.data["position"] for c in rec("cover.set_cover_position", COVER)] == [100]

    await advance(hass, freezer, msk(9, 6, 57, 58), step=5)
    assert rec("media_player.play_media") == []
    await advance(hass, freezer, msk(9, 6, 58, 2))
    assert 0.05 <= rec("media_player.volume_set")[0].data["volume_level"] <= 0.07
    play = rec("media_player.play_media", STATION)
    assert len(play) == 1
    assert play[0].data["media_content_type"] == "command"
    assert play[0].data["media_content_id"] == "включи мою волну"

    await advance(hass, freezer, msk(9, 6, 59, 58), step=5)
    assert rec("switch.turn_on") == []
    assert rec("light.turn_on", ONOFF_LIGHT) == []
    brightness = rec.brightness()
    assert brightness == sorted(brightness)
    assert len(set(brightness)) == len(brightness)
    assert 230 < brightness[-1] < 255

    await advance(hass, freezer, msk(9, 7, 0, 2))
    assert ctl.state == AlarmState.RINGING
    assert rec.brightness()[-1] == 255
    assert len(rec("switch.turn_on", PLUG)) == 1
    assert len(rec("light.turn_on", ONOFF_LIGHT)) == 1
    assert "brightness" not in rec("light.turn_on", ONOFF_LIGHT)[0].data
    volumes = [c.data["volume_level"] for c in rec("media_player.volume_set")]
    assert volumes == sorted(volumes)
    assert volumes[-1] == 0.5
    assert EVENT_RINGING in rec.event_types()
    assert len(rec("cover.set_cover_position")) == 1


async def test_dimmer_already_on_is_not_dimmed(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set(DIMMER, "on", {"supported_color_modes": ["brightness"], "brightness": 153})
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 56), step=5)
    # Curve reaches 153 at ~79% of the fade (~06:56:50)
    assert rec.brightness() == []
    await advance(hass, freezer, msk(9, 7, 0, 2), step=5)
    assert rec.brightness()
    assert min(rec.brightness()) > 153
    assert rec.brightness()[-1] == 255


async def test_only_non_dimmable_sources(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    await setup_alarm(hass, sources=[PLUG, ONOFF_LIGHT], covers=[])
    await advance(hass, freezer, msk(9, 6, 59, 58), step=10)
    assert rec("light.turn_on") == []
    assert rec("switch.turn_on") == []
    await advance(hass, freezer, msk(9, 7, 0, 2))
    assert len(rec("switch.turn_on", PLUG)) == 1
    assert len(rec("light.turn_on", ONOFF_LIGHT)) == 1


async def test_winter_covers_stay_closed(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set("sun.sun", "below_horizon", {"elevation": -12.0})
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 7, 1), step=10)
    assert rec("cover.set_cover_position") == []
    assert rec("cover.open_cover") == []


async def test_sun_rises_inside_window(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set("sun.sun", "below_horizon", {"elevation": -1.0})
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 52), step=10)
    assert rec("cover.set_cover_position") == []
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 0.1})
    await hass.async_block_till_done()
    assert len(rec("cover.set_cover_position")) == 1
    await advance(hass, freezer, msk(9, 7, 1), step=10)
    assert len(rec("cover.set_cover_position")) == 1


async def test_cover_without_position_support(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set(COVER, "closed", {"supported_features": 3})
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 45, 5), step=60)
    assert len(rec("cover.open_cover", COVER)) == 1


async def test_unavailable_player_does_not_break_sequence(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set(STATION, "unavailable")
    await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 7, 0, 2), step=10)
    assert rec("media_player.play_media") == []
    assert rec("media_player.volume_set") == []
    assert rec.brightness()[-1] == 255
    assert len(rec("switch.turn_on", PLUG)) == 1


async def test_change_media_lead_on_the_fly(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 30))
    entry = await setup_alarm(hass)
    controller(entry).set_setting(SET_MEDIA_LEAD, 10)
    await advance(hass, freezer, msk(9, 6, 49, 58), step=10)
    assert rec("media_player.play_media") == []
    await advance(hass, freezer, msk(9, 6, 50, 6))  # one tick of slack
    assert len(rec("media_player.play_media")) == 1


async def test_media_lead_longer_than_remaining_starts_now(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await advance(hass, freezer, msk(9, 6, 55), step=10)
    assert rec("media_player.play_media") == []
    controller(entry).set_setting(SET_MEDIA_LEAD, 10)
    await advance(hass, freezer, msk(9, 6, 55, 6))
    assert len(rec("media_player.play_media")) == 1
    # Halfway through the 10 minute window: 0.05 + (0.5 - 0.05) * 0.5
    assert 0.27 <= rec("media_player.volume_set")[0].data["volume_level"] <= 0.29


async def test_change_fade_on_the_fly(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 30))
    entry = await setup_alarm(hass, covers=[])
    controller(entry).set_setting(SET_FADE, 25)
    await advance(hass, freezer, msk(9, 6, 34, 58), step=10)
    assert rec("light.turn_on") == []
    await advance(hass, freezer, msk(9, 6, 35, 2))
    assert rec.brightness() == [1]


async def test_covers_regardless_of_sun_when_option_off(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set("sun.sun", "below_horizon", {"elevation": -12.0})
    entry = await setup_alarm(hass)
    controller(entry).set_setting("cover_sun_only", False)
    await advance(hass, freezer, msk(9, 6, 44, 58), step=60)
    assert rec("cover.set_cover_position") == []
    await advance(hass, freezer, msk(9, 6, 45, 2))
    assert [c.data["position"] for c in rec("cover.set_cover_position", COVER)] == [100]
    await advance(hass, freezer, msk(9, 7, 1), step=10)
    assert len(rec("cover.set_cover_position")) == 1


async def test_sun_only_switch_entity(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    switch = entity_id(hass, entry, "switch", "cover_sun_only")
    assert hass.states.get(switch).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert controller(entry).settings["cover_sun_only"] is False
