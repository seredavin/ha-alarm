"""The dashboard card is served and loaded by the integration."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.wakeup_alarm.card import CARD_URL

from .common import setup_alarm


async def test_card_is_served(hass: HomeAssistant, hass_client) -> None:
    await setup_alarm(hass, enabled=False)
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    body = await response.text()
    assert "customElements.define(CARD_TYPE" in body
    assert "wakeup-alarm-card-editor" in body


async def test_card_added_to_frontend_once(hass: HomeAssistant) -> None:
    hass.config.components.add("frontend")
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_url:
        await setup_alarm(hass, title="First", enabled=False)
        await setup_alarm(hass, title="Second", enabled=False)
    add_url.assert_called_once()
    assert add_url.call_args.args[1] == f"{CARD_URL}?v=0.2.0"
