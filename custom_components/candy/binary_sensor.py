from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .client.model import TumbleDryerStatus, WashingMachineStatus
from .const import (
    DATA_KEY_COORDINATOR,
    DOMAIN,
    UNIQUE_ID_TUMBLE_CLEAN_FILTER,
    UNIQUE_ID_TUMBLE_DOOR,
    UNIQUE_ID_TUMBLE_REMOTE_CONTROL,
    UNIQUE_ID_TUMBLE_WATER_TANK,
    UNIQUE_ID_WASH_REMOTE_CONTROL,
)
from .helpers import dryer_device_info, wash_device_info


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Candy binary sensors from config entry."""

    config_id = config_entry.entry_id
    coordinator = hass.data[DOMAIN][config_id][DATA_KEY_COORDINATOR]

    if isinstance(coordinator.data, WashingMachineStatus):
        async_add_entities(
            [CandyWashRemoteControlBinarySensor(coordinator, config_entry)]
        )
    elif isinstance(coordinator.data, TumbleDryerStatus):
        async_add_entities(
            [
                CandyTumbleRemoteControlBinarySensor(coordinator, config_entry),
                CandyTumbleDoorBinarySensor(coordinator, config_entry),
                CandyTumbleCleanFilterBinarySensor(coordinator, config_entry),
                CandyTumbleWaterTankBinarySensor(coordinator, config_entry),
            ]
        )


class CandyWashRemoteControlBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_translation_key = "remote_control"
    _attr_name = "Remote control"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:remote"

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.config_id = config_entry.entry_id

    @property
    def unique_id(self) -> str:
        return UNIQUE_ID_WASH_REMOTE_CONTROL.format(self.config_id)

    @property
    def device_info(self) -> DeviceInfo:
        return wash_device_info(self.config_entry)

    @property
    def is_on(self) -> bool | None:
        if not isinstance(self.coordinator.data, WashingMachineStatus):
            return None
        return self.coordinator.data.remote_control


class CandyTumbleRemoteControlBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "remote_control"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:remote"

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.config_id = config_entry.entry_id

    @property
    def unique_id(self) -> str:
        return UNIQUE_ID_TUMBLE_REMOTE_CONTROL.format(self.config_id)

    @property
    def device_info(self) -> DeviceInfo:
        return dryer_device_info(self.config_entry)

    @property
    def is_on(self) -> bool | None:
        if not isinstance(self.coordinator.data, TumbleDryerStatus):
            return None
        return self.coordinator.data.remote_control


class CandyTumbleDoorBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "door"
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.config_id = config_entry.entry_id

    @property
    def unique_id(self) -> str:
        return UNIQUE_ID_TUMBLE_DOOR.format(self.config_id)

    @property
    def device_info(self) -> DeviceInfo:
        return dryer_device_info(self.config_entry)

    @property
    def is_on(self) -> bool | None:
        if not isinstance(self.coordinator.data, TumbleDryerStatus):
            return None
        return not self.coordinator.data.door_closed


class CandyTumbleCleanFilterBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "clean_filter"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.config_id = config_entry.entry_id

    @property
    def unique_id(self) -> str:
        return UNIQUE_ID_TUMBLE_CLEAN_FILTER.format(self.config_id)

    @property
    def device_info(self) -> DeviceInfo:
        return dryer_device_info(self.config_entry)

    @property
    def is_on(self) -> bool | None:
        if not isinstance(self.coordinator.data, TumbleDryerStatus):
            return None
        return self.coordinator.data.need_clean_filter


class CandyTumbleWaterTankBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "water_tank_full"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: DataUpdateCoordinator, config_entry: ConfigEntry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self.config_id = config_entry.entry_id

    @property
    def unique_id(self) -> str:
        return UNIQUE_ID_TUMBLE_WATER_TANK.format(self.config_id)

    @property
    def device_info(self) -> DeviceInfo:
        return dryer_device_info(self.config_entry)

    @property
    def is_on(self) -> bool | None:
        if not isinstance(self.coordinator.data, TumbleDryerStatus):
            return None
        return self.coordinator.data.water_tank_full
