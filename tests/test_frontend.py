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
    assert add_url.call_args.args[1] == f"{CARD_URL}?v=0.2.3"


async def _resources(hass: HomeAssistant):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data["lovelace"].resources
    await resources.async_get_info()
    return resources


async def test_card_registered_as_lovelace_resource(hass: HomeAssistant) -> None:
    resources = await _resources(hass)
    await setup_alarm(hass, enabled=False)
    urls = [item["url"] for item in resources.async_items()]
    assert urls == [f"{CARD_URL}?v=0.2.3"]
    assert resources.async_items()[0]["type"] == "module"


async def test_resource_updated_to_new_version(hass: HomeAssistant) -> None:
    resources = await _resources(hass)
    await resources.async_create_item({"res_type": "module", "url": f"{CARD_URL}?v=0.0.1"})
    await resources.async_create_item({"res_type": "module", "url": "/local/other.js"})
    await setup_alarm(hass, enabled=False)
    urls = sorted(item["url"] for item in resources.async_items())
    assert urls == ["/local/other.js", f"{CARD_URL}?v=0.2.3"]


async def test_resource_removed_with_last_alarm(hass: HomeAssistant) -> None:
    resources = await _resources(hass)
    first = await setup_alarm(hass, title="First", enabled=False)
    second = await setup_alarm(hass, title="Second", enabled=False)
    await hass.config_entries.async_remove(first.entry_id)
    assert len(resources.async_items()) == 1
    await hass.config_entries.async_remove(second.entry_id)
    assert resources.async_items() == []
