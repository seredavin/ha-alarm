"""Greeting phrase."""

from __future__ import annotations

import pytest

from custom_components.wakeup_alarm.greeting import build_greeting, degrees_word, round_half_up


@pytest.mark.parametrize(
    ("value", "word"),
    [
        (1, "градус"),
        (2, "градуса"),
        (4, "градуса"),
        (5, "градусов"),
        (11, "градусов"),
        (12, "градусов"),
        (21, "градус"),
        (22, "градуса"),
        (-3, "градуса"),
        (0, "градусов"),
        (111, "градусов"),
    ],
)
def test_degrees_word(value: int, word: str) -> None:
    assert degrees_word(value) == word


def test_round_half_up() -> None:
    assert [round_half_up(x) for x in (2.5, 2.4, -2.5, -0.4, 7.2)] == [3, 2, -3, 0, 7]


def test_full_phrase() -> None:
    assert build_greeting("cloudy", 2.6, 7.2) == "Доброе утро! Сейчас плюс 3 градуса, облачно. Днём до плюс 7."


def test_frost_and_zero() -> None:
    assert build_greeting("snowy", -11.4, 0.3) == "Доброе утро! Сейчас минус 11 градусов, снег. Днём до нуля."
    assert build_greeting("fog", 0.2, None) == "Доброе утро! Сейчас ноль градусов, туман."


def test_unknown_condition_and_missing_data() -> None:
    assert build_greeting("weird", 1, None) == "Доброе утро! Сейчас плюс 1 градус."
    assert build_greeting(None, None, None) == "Доброе утро!"
    assert build_greeting("sunny", None, 20) == "Доброе утро! Сейчас солнечно. Днём до плюс 20."
