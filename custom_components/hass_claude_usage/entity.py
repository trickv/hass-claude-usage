"""Shared entity helpers for Claude Usage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import CONF_ACCOUNT_NAME, CONF_SUBSCRIPTION_LEVEL, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the single service device shared by every entity of an entry.

    The name carries the account and plan so multiple entries stay tellable
    apart in the UI: "Claude Usage (Alice - max_20x)".
    """
    account_name = entry.data.get(CONF_ACCOUNT_NAME)
    subscription_level = entry.data.get(CONF_SUBSCRIPTION_LEVEL)

    device_name = "Claude Usage"
    if account_name:
        suffix = f" - {subscription_level}" if subscription_level else ""
        device_name = f"{device_name} ({account_name}{suffix})"

    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=device_name,
        entry_type=DeviceEntryType.SERVICE,
    )
