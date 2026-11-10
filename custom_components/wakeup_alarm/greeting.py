"""Morning greeting phrase (pure functions, Russian)."""

from __future__ import annotations

import math

CONDITIONS = {
    "sunny": "солнечно",
    "clear-night": "ясно",
    "partlycloudy": "переменная облачность",
    "cloudy": "облачно",
    "rainy": "дождь",
    "pouring": "ливень",
    "snowy": "снег",
    "snowy-rainy": "мокрый снег",
    "fog": "туман",
    "hail": "град",
    "lightning": "гроза",
    "lightning-rainy": "гроза с дождём",
    "windy": "ветрено",
    "windy-variant": "ветрено",
    "exceptional": "необычная погода",
}


def round_half_up(value: float) -> int:
    """Round 2.5 to 3 and -2.5 to -3 (Python's round() would give 2 and -2)."""
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def degrees_word(value: int) -> str:
    """Return градус/градуса/градусов for a number."""
    n = abs(value) % 100
    if 11 <= n <= 14:
        return "градусов"
    last = n % 10
    if last == 1:
        return "градус"
    if 2 <= last <= 4:
        return "градуса"
    return "градусов"


def signed(value: int) -> str:
    """Return 'плюс 3' / 'минус 3' / 'ноль'."""
    if value == 0:
        return "ноль"
    return f"{'плюс' if value > 0 else 'минус'} {abs(value)}"


def build_greeting(condition: str | None, temperature: float | None, high: float | None) -> str:
    """Build e.g. 'Доброе утро! Сейчас плюс 3 градуса, облачно. Днём до плюс 7.'."""
    parts = ["Доброе утро!"]
    weather = CONDITIONS.get(condition or "")
    if temperature is not None:
        now = round_half_up(temperature)
        sentence = f"Сейчас {signed(now)} {degrees_word(now)}"
        if weather:
            sentence += f", {weather}"
        parts.append(sentence + ".")
    elif weather:
        parts.append(f"Сейчас {weather}.")
    if high is not None:
        top = round_half_up(high)
        parts.append("Днём до нуля." if top == 0 else f"Днём до {signed(top)}.")
    return " ".join(parts)
