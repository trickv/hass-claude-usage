"""Sensor platform for Claude Usage integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ClaudeUsageConfigEntry, ClaudeUsageCoordinator
from .const import (
    CONF_ACCOUNT_NAME,
    CONF_SUBSCRIPTION_LEVEL,
    DOMAIN,
    SENSOR_DEFINITIONS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClaudeUsageConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Claude Usage sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        ClaudeUsageSensor(coordinator, entry, key, name, unit, icon, device_class)
        for key, name, unit, icon, device_class in SENSOR_DEFINITIONS
    )

    # Dynamic per-bucket limit sensors from the payload's limits[] array.
    # Buckets can appear at any time (new model, new surface, plan change),
    # so re-sync on every coordinator update and add entities for unseen
    # bucket keys. Buckets that later VANISH from the payload are never
    # removed — their sensors read unavailable and recorder history survives.
    known_limit_keys: set[str] = set()

    def _sync_limit_entities() -> None:
        limits = (coordinator.data or {}).get("limits") or {}
        new_entities = [
            ClaudeUsageLimitSensor(coordinator, entry, key, meta["label"])
            for key, meta in limits.items()
            if key not in known_limit_keys
        ]
        if new_entities:
            known_limit_keys.update(e.limit_key for e in new_entities)
            async_add_entities(new_entities)

    _sync_limit_entities()
    entry.async_on_unload(coordinator.async_add_listener(_sync_limit_entities))


class ClaudeUsageSensor(CoordinatorEntity[ClaudeUsageCoordinator], SensorEntity):
    """A sensor for a Claude usage metric."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ClaudeUsageCoordinator,
        entry: ClaudeUsageConfigEntry,
        key: str,
        name: str,
        unit: str | None,
        icon: str,
        device_class: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._is_timestamp = device_class == "timestamp"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        if self._is_timestamp:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif unit is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT

        # Build device name with account name and subscription level
        account_name = entry.data.get(CONF_ACCOUNT_NAME)
        subscription_level = entry.data.get(CONF_SUBSCRIPTION_LEVEL)

        device_name_parts = ["Claude Usage"]
        if account_name:
            device_name_parts.append(f"({account_name}")
            if subscription_level:
                device_name_parts.append(f"- {subscription_level})")
            else:
                device_name_parts[-1] += ")"
        device_name = " ".join(device_name_parts)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Return True if the sensor value is present in coordinator data."""
        if self._key == "api_error":
            return True
        if not super().available:
            return False
        if self.coordinator.data is None:
            return False
        return self._key in self.coordinator.data

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self._key == "api_error":
            return 0 if self.coordinator.last_update_success else 1
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._key)
        if value is not None and self._is_timestamp:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid timestamp value for %s: %s", self._key, value)
                return None
        return value


class ClaudeUsageLimitSensor(CoordinatorEntity[ClaudeUsageCoordinator], SensorEntity):
    """A dynamically-created sensor for one bucket of the limits[] array.

    State is the bucket's percent; resets_at / severity / is_active and the
    scope fields ride along as attributes. The reset time is deliberately an
    attribute rather than a companion sensor so a payload with many scoped
    buckets doesn't double the entity count.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(
        self,
        coordinator: ClaudeUsageCoordinator,
        entry: ClaudeUsageConfigEntry,
        key: str,
        label: str,
    ) -> None:
        """Initialize the limit sensor."""
        super().__init__(coordinator)
        self.limit_key = key
        self._attr_unique_id = f"{entry.entry_id}_limit_{key}"
        self._attr_name = f"{label} Usage"

        account_name = entry.data.get(CONF_ACCOUNT_NAME)
        subscription_level = entry.data.get(CONF_SUBSCRIPTION_LEVEL)
        device_name_parts = ["Claude Usage"]
        if account_name:
            device_name_parts.append(f"({account_name}")
            if subscription_level:
                device_name_parts.append(f"- {subscription_level})")
            else:
                device_name_parts[-1] += ")"
        device_name = " ".join(device_name_parts)

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _bucket(self) -> dict[str, Any] | None:
        limits = (self.coordinator.data or {}).get("limits") or {}
        return limits.get(self.limit_key)

    @property
    def available(self) -> bool:
        """Available while the bucket is present in the current payload."""
        return super().available and self._bucket() is not None

    @property
    def native_value(self) -> Any:
        """Return the bucket's percent."""
        bucket = self._bucket()
        return None if bucket is None else bucket.get("percent")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the rest of the bucket alongside the percent."""
        bucket = self._bucket()
        if bucket is None:
            return None
        return {
            "resets_at": bucket.get("resets_at"),
            "severity": bucket.get("severity"),
            "is_active": bucket.get("is_active"),
            "kind": bucket.get("kind"),
            "group": bucket.get("group"),
            "model": bucket.get("model"),
            "surface": bucket.get("surface"),
        }
