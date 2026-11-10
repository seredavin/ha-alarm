"""Constants for the Wake-up Alarm integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final = "wakeup_alarm"

# Config entry options (devices and sequence behaviour)
CONF_SOURCES: Final = "sources"
CONF_MEDIA_PLAYER: Final = "media_player"
CONF_COVERS: Final = "covers"
CONF_MEDIA_TYPE: Final = "media_type"
CONF_MEDIA_ID: Final = "media_id"
CONF_START_VOLUME: Final = "start_volume"
CONF_COVER_POSITION: Final = "cover_position"
CONF_SUN_ELEVATION: Final = "sun_elevation"
CONF_STOP_ON_CHANGE: Final = "stop_on_change"

DEFAULT_MEDIA_TYPE: Final = "command"
DEFAULT_MEDIA_ID: Final = "включи мою волну"
DEFAULT_START_VOLUME: Final = 5
DEFAULT_COVER_POSITION: Final = 100
DEFAULT_SUN_ELEVATION: Final = 0.0
DEFAULT_STOP_ON_CHANGE: Final = True

# Runtime settings, exposed as entities and persisted in Store
SET_ENABLED: Final = "enabled"
SET_SKIP_NEXT: Final = "skip_next"
SET_WEEKDAYS: Final = "weekdays"
SET_WAKE_TIME: Final = "wake_time"
SET_FADE: Final = "fade_duration"
SET_MEDIA_LEAD: Final = "media_lead"
SET_MAX_VOLUME: Final = "max_volume"
SET_COVER_LEAD: Final = "cover_lead"
SET_SNOOZE: Final = "snooze_duration"
SET_AUTO_STOP: Final = "auto_stop"
SET_COVER_SUN_ONLY: Final = "cover_sun_only"

WEEKDAY_KEYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

DEFAULT_SETTINGS: Final = {
    SET_ENABLED: False,
    SET_SKIP_NEXT: False,
    SET_WEEKDAYS: [True, True, True, True, True, False, False],
    SET_WAKE_TIME: "07:00:00",
    SET_FADE: 15,
    SET_MEDIA_LEAD: 2,
    SET_MAX_VOLUME: 50,
    SET_COVER_LEAD: 15,
    SET_SNOOZE: 9,
    SET_AUTO_STOP: 30,
    SET_COVER_SUN_ONLY: True,
}

# Settings that change when the alarm fires (others only affect a run)
SCHEDULE_SETTINGS: Final = frozenset(
    {SET_ENABLED, SET_SKIP_NEXT, SET_WEEKDAYS, SET_WAKE_TIME, SET_FADE, SET_MEDIA_LEAD, SET_COVER_LEAD}
)

STORAGE_VERSION: Final = 1

TICK_INTERVAL: Final = 5.0  # seconds
ECHO_WINDOW: Final = 5.0  # seconds after own command when device updates are ignored
BRIGHTNESS_TOLERANCE: Final = 13  # ~5% of 255
MEDIA_GRACE: Final = 15.0  # seconds after play_media before pauses count as manual
MEDIA_DEBOUNCE: Final = 5.0  # seconds a player must stay not-playing to count as manual
GAMMA: Final = 2.2


class AlarmState(StrEnum):
    """State of an alarm."""

    OFF = "off"
    SCHEDULED = "scheduled"
    SUNRISE = "sunrise"
    RINGING = "ringing"
    SNOOZED = "snoozed"


ACTIVE_STATES: Final = frozenset({AlarmState.SUNRISE, AlarmState.RINGING, AlarmState.SNOOZED})


class StopReason(StrEnum):
    """Why a run was stopped."""

    BUTTON = "button"
    SERVICE = "service"
    AUTO = "auto"
    MANUAL = "manual"
    DISABLED = "disabled"


EVENT_SUNRISE_STARTED: Final = f"{DOMAIN}_sunrise_started"
EVENT_RINGING: Final = f"{DOMAIN}_ringing"
EVENT_SNOOZED: Final = f"{DOMAIN}_snoozed"
EVENT_STOPPED: Final = f"{DOMAIN}_stopped"

SERVICE_STOP: Final = "stop"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_TRIGGER: Final = "trigger"
ATTR_DURATION: Final = "duration"
