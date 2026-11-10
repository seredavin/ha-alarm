"""Speaker content, cloud-only speakers and the good morning greeting."""

from __future__ import annotations

from datetime import timedelta
import itertools

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.util import dt as dt_util

from custom_components.wakeup_alarm.const import AlarmState

from .common import STATION, advance, controller, entity_id, msk, setup_alarm, setup_world


def timed_player(hass: HomeAssistant) -> list[tuple[str, dict, object]]:
    """Replace speaker mocks with ones that record when each call happened."""
    log: list[tuple[str, dict, object]] = []
    for service in ("volume_set", "play_media", "media_stop", "media_pause"):

        async def handler(call: ServiceCall, service: str = service) -> None:
            log.append((service, dict(call.data), dt_util.utcnow()))

        hass.services.async_register("media_player", service, handler)
    return log


def plays(log) -> list[str]:
    return [d["media_content_id"] for s, d, _ in log if s == "play_media"]


async def test_preset_command(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id(hass, entry, "select", "media_preset"), "option": "nature"},
        blocking=True,
    )
    await advance(hass, freezer, msk(9, 6, 58, 6), step=10)
    assert [c.data["media_content_id"] for c in rec("media_player.play_media")] == ["включи звуки природы"]


async def test_custom_command_and_empty_fallback(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass)
    ctl = controller(entry)
    ctl.set_setting("media_preset", "custom")
    assert ctl.media_command == "включи мою волну"  # empty custom text
    await hass.services.async_call(
        "text",
        "set_value",
        {"entity_id": entity_id(hass, entry, "text", "media_custom"), "value": " включи радио Максимум "},
        blocking=True,
    )
    assert ctl.media_command == "включи радио Максимум"


async def test_legacy_media_id_migrates(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    entry = await setup_alarm(hass, media_id="включи радио")
    ctl = controller(entry)
    assert ctl.settings["media_preset"] == "custom"
    assert ctl.settings["media_custom"] == "включи радио"
    default = await setup_alarm(hass, title="Default", media_id="включи мою волну")
    assert controller(default).settings["media_preset"] == "wave"


async def test_cloud_speaker_steps(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set(STATION, "idle", {"volume_level": 0.3, "assumed_state": True})
    log = timed_player(hass)
    entry = await setup_alarm(hass, covers=[])
    await advance(hass, freezer, msk(9, 7, 0, 30), step=1)
    commands = [(s, d.get("volume_level", d.get("media_content_id")), t) for s, d, t in log]
    volumes = [v for s, v, _ in commands if s == "volume_set"]
    assert volumes == [0.1, 0.2, 0.3, 0.4, 0.5]
    assert commands[0][0] == "volume_set" and commands[1][0] == "play_media"
    assert (commands[1][2] - commands[0][2]).total_seconds() >= 3
    times = [t for _, _, t in commands]
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times[1:])]
    assert all(gap >= 10 for gap in gaps), gaps
    assert times[-1] <= msk(9, 7, 0, 1)
    # A cloud speaker reporting idle is not taken as "someone stopped it"
    assert controller(entry).state == AlarmState.RINGING


async def test_cloud_speaker_catches_up_after_wake(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await setup_world(hass, freezer, msk(9, 6, 0))
    hass.states.async_set(STATION, "idle", {"volume_level": 0.3, "assumed_state": True})
    log = timed_player(hass)
    entry = await setup_alarm(hass, covers=[])
    controller(entry).set_setting("media_lead", 0)  # starts at the wake moment, at max volume
    controller(entry).set_setting("max_volume", 80)
    await advance(hass, freezer, msk(9, 7, 0, 30), step=1)
    assert [d.get("volume_level") for s, d, _ in log if s == "volume_set"] == [0.8]
    assert plays(log) == ["включи мою волну"]


async def test_local_speaker_unchanged(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    rec = await setup_world(hass, freezer, msk(9, 6, 0))
    await setup_alarm(hass, covers=[])
    await advance(hass, freezer, msk(9, 7, 0, 5), step=5)
    volumes = [c.data["volume_level"] for c in rec("media_player.volume_set")]
    assert len(volumes) > 10  # smooth, not whole steps
    assert volumes[0] < 0.1


def mock_weather(hass: HomeAssistant, high: float | None = 7.2) -> None:
    hass.states.async_set("weather.home", "cloudy", {"temperature": 2.6})

    async def forecasts(call: ServiceCall) -> dict:
        if call.data["type"] != "daily" or high is None:
            raise ValueError("unsupported")
        today = dt_util.now().replace(hour=12)
        return {
            "weather.home": {
                "forecast": [
                    {"datetime": today.isoformat(), "temperature": high},
                    {"datetime": (today + timedelta(days=1)).isoformat(), "temperature": 1.0},
                ]
            }
        }

    hass.services.async_register("weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY)


async def ringing_with_player(hass, freezer, **options):
    await setup_world(hass, freezer, msk(9, 6, 0))
    log = timed_player(hass)
    entry = await setup_alarm(hass, covers=[], **options)
    await advance(hass, freezer, msk(9, 7, 0, 5), step=5)
    hass.states.async_set(STATION, "playing", {"volume_level": 0.5})
    await hass.async_block_till_done()
    log.clear()
    return entry, log


async def test_greeting_after_stop_button(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry, log = await ringing_with_player(hass, freezer)
    mock_weather(hass)
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id(hass, entry, "button", "stop")}, blocking=True
    )
    await advance(hass, freezer, dt_util.now() + timedelta(seconds=5))
    assert [s for s, _, _ in log] == ["media_stop", "volume_set", "play_media"]
    assert log[1][1]["volume_level"] == 0.2
    assert log[2][1] == {
        "entity_id": STATION,
        "media_content_type": "text",
        "media_content_id": "Доброе утро! Сейчас плюс 3 градуса, облачно. Днём до плюс 7.",
    }
    assert (log[2][2] - log[1][2]).total_seconds() >= 3


async def test_greeting_without_forecast(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry, log = await ringing_with_player(hass, freezer)
    mock_weather(hass, high=None)
    controller(entry).async_stop()
    await advance(hass, freezer, dt_util.now() + timedelta(seconds=5))
    assert plays(log) == ["Доброе утро! Сейчас плюс 3 градуса, облачно."]


async def test_no_greeting_on_auto_stop(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry, log = await ringing_with_player(hass, freezer)
    await advance(hass, freezer, msk(9, 7, 30, 10), step=30)
    assert controller(entry).state == AlarmState.SCHEDULED
    assert plays(log) == []
    assert [s for s, _, _ in log] == ["media_stop", "volume_set"]


async def test_no_greeting_when_switched_off(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry, log = await ringing_with_player(hass, freezer)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id(hass, entry, "switch", "greeting")}, blocking=True
    )
    controller(entry).async_stop()
    await advance(hass, freezer, dt_util.now() + timedelta(seconds=5))
    assert plays(log) == []


async def test_weather_option_used(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    entry, log = await ringing_with_player(hass, freezer, weather="weather.other")
    mock_weather(hass)
    hass.states.async_set("weather.other", "sunny", {"temperature": -1})
    controller(entry).async_stop()
    await advance(hass, freezer, dt_util.now() + timedelta(seconds=5))
    assert plays(log) == ["Доброе утро! Сейчас минус 1 градус, солнечно."]
