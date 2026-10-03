from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo

from .client import parse_wash_programs
from .client.model import WashingMachineStatus, WashingMachineWashProgram
from .const import (
    CONF_KEY_BRAND,
    CONF_KEY_DEVICE_MODEL,
    CONF_KEY_IS_WASHER_DRYER,
    CONF_KEY_MAC_ADDRESS,
    CONF_KEY_MODE,
    CONF_KEY_PROGRAMS,
    CONF_KEY_SERIAL_NUMBER,
    DEVICE_NAME_WASHER_DRYER,
    DEVICE_NAME_WASHING_MACHINE,
    DOMAIN,
    MODE_FULL_CONTROL,
    SUGGESTED_AREA_BATHROOM,
)

_NOTIFICATION_STRINGS: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "client" / "notification_strings.json").read_text(
        encoding="utf-8"
    )
)


def localized_notification_text(key: str, language: str) -> str:
    """Return the notification string for key, falling back to English."""
    translations = _NOTIFICATION_STRINGS[key]
    return translations.get(language, translations["en"])


def remote_control_enabled(data: object) -> bool:
    """Return True when the washing machine accepts remote commands."""
    return isinstance(data, WashingMachineStatus) and data.remote_control


def cycles_remaining(total: int, last_reset: int, threshold: int) -> int:
    """Return cycles until next maintenance alert, or 0 when due (including overdue).

    Returns 0 for any elapsed >= threshold so notifications fire on every wash
    until the user manually resets the counter.
    """
    elapsed = total - last_reset
    if elapsed <= 0:
        return threshold
    if elapsed >= threshold:
        return 0
    return threshold - elapsed


def is_washer_dryer(
    config_entry: ConfigEntry,
    programs: list[WashingMachineWashProgram] | None,
) -> bool:
    """Return True if the config entry represents a washer-dryer appliance."""
    if config_entry.data.get(CONF_KEY_IS_WASHER_DRYER, False):
        return True
    if programs is not None:
        return any(p.is_dry for p in programs)
    raw_programs = config_entry.data.get(CONF_KEY_PROGRAMS, [])
    if raw_programs:
        try:
            return any(p.is_dry for p in parse_wash_programs(raw_programs))
        except (KeyError, TypeError, ValueError):
            return False
    return False


def wash_device_name(config_entry: ConfigEntry) -> str:
    if is_washer_dryer(config_entry, None):
        return DEVICE_NAME_WASHER_DRYER
    return DEVICE_NAME_WASHING_MACHINE


def wash_device_info(config_entry: ConfigEntry) -> DeviceInfo:
    brand = config_entry.data.get(CONF_KEY_BRAND, "candy")
    manufacturer = brand.capitalize() if brand else "Candy"
    info = DeviceInfo(
        identifiers={(DOMAIN, config_entry.entry_id)},
        name=wash_device_name(config_entry),
        manufacturer=manufacturer,
        suggested_area=SUGGESTED_AREA_BATHROOM,
    )
    if config_entry.data.get(CONF_KEY_MAC_ADDRESS):
        info["connections"] = {
            (
                dr.CONNECTION_NETWORK_MAC,
                config_entry.data[CONF_KEY_MAC_ADDRESS],
            )
        }
    if config_entry.data.get(CONF_KEY_MODE) == MODE_FULL_CONTROL:
        if config_entry.data.get(CONF_KEY_DEVICE_MODEL):
            info["model"] = config_entry.data[CONF_KEY_DEVICE_MODEL]
        if config_entry.data.get(CONF_KEY_SERIAL_NUMBER):
            info["serial_number"] = config_entry.data[CONF_KEY_SERIAL_NUMBER]
    return info


def get_wash_error_notification_strings(
    error_code: int, language: str
) -> tuple[str, str] | None:
    """Return (title, message) for washing machine error, or None if unknown code."""
    msg_key = f"wash_error_{error_code}_message"
    if msg_key not in _NOTIFICATION_STRINGS:
        return None
    base_title = localized_notification_text("wash_error_title", language)
    title = f"{base_title}: E{error_code:02d}"
    message = localized_notification_text(msg_key, language)
    return title, message
