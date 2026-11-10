"""Serve the Lovelace card shipped with the integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "wakeup-alarm-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
CARD_PATH = Path(__file__).parent / "frontend" / CARD_FILENAME
DATA_CARD_REGISTERED = f"{DOMAIN}_card_registered"
LOVELACE_DOMAIN = "lovelace"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and load it in the frontend (once per process).

    The card is added both as an extra frontend module and as a Lovelace resource
    with the same URL (the browser imports it once). Extra modules only come from
    index.html, which a service worker may serve from cache without the card;
    Lovelace resources are fetched by every dashboard on load.
    """
    if hass.data.get(DATA_CARD_REGISTERED):
        return
    hass.data[DATA_CARD_REGISTERED] = True
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_PATH), False)])
    integration = await async_get_integration(hass, DOMAIN)
    url = f"{CARD_URL}?v={integration.version}"
    if "frontend" in hass.config.components:
        # frontend is optional (after_dependency), so import it only when loaded
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, url)
    await _async_sync_resource(hass, url)


def _storage_resources(hass: HomeAssistant) -> Any | None:
    """Return the Lovelace resource collection if resources are UI-managed."""
    data = hass.data.get(LOVELACE_DOMAIN)
    resources = getattr(data, "resources", None)
    if getattr(data, "resource_mode", None) != "storage" or not hasattr(resources, "async_create_item"):
        return None
    return resources


async def _async_sync_resource(hass: HomeAssistant, url: str) -> None:
    """Create or update our Lovelace resource so it points at the current version."""
    resources = _storage_resources(hass)
    if resources is None:
        return
    try:
        await resources.async_get_info()  # loads the collection from storage
        for item in resources.async_items():
            if item["url"].split("?", 1)[0] == CARD_URL:
                if item["url"] != url:
                    await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
                return
        await resources.async_create_item({"res_type": "module", "url": url})
    except Exception:  # the extra module still loads the card
        _LOGGER.warning("Could not register the card as a Lovelace resource", exc_info=True)


async def async_unregister_card_resource(hass: HomeAssistant) -> None:
    """Remove our Lovelace resource (when the last alarm is deleted)."""
    resources = _storage_resources(hass)
    if resources is None:
        return
    try:
        await resources.async_get_info()
        for item in list(resources.async_items()):
            if item["url"].split("?", 1)[0] == CARD_URL:
                await resources.async_delete_item(item["id"])
    except Exception:
        _LOGGER.warning("Could not remove the card Lovelace resource", exc_info=True)
