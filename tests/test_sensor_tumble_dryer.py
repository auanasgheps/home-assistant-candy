"""Tests for various sensors."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
from pytest_homeassistant_custom_component.common import load_fixture
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .common import init_integration


async def test_main_sensor_idle(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(hass, aioclient_mock, load_fixture("tumble_dryer/idle.json"))

    state = hass.states.get("sensor.tumble_dryer")

    assert state
    assert state.state == "Idle"
    assert state.attributes == {
        "program": 1,
        "remaining_minutes": 150,
        "remote_control": True,
        "dry_level": 2,
        "dry_level_now": 1,
        "refresh": False,
        "need_clean_filter": False,
        "water_tank_full": False,
        "door_closed": True,
        "friendly_name": "Tumble dryer",
        "icon": "mdi:tumble-dryer",
    }


async def test_program_sensor_idle(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(hass, aioclient_mock, load_fixture("tumble_dryer/idle.json"))

    state = hass.states.get("sensor.dryer_program")

    assert state
    assert state.state == "1"
    assert state.attributes == {
        "friendly_name": "Dryer program",
        "icon": "mdi:tumble-dryer",
    }


async def test_main_sensor_running(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(
        hass, aioclient_mock, load_fixture("tumble_dryer/running.json")
    )

    state = hass.states.get("sensor.tumble_dryer")

    assert state
    assert state.state == "Running"
    assert state.attributes == {
        "program": 1,
        "remaining_minutes": 150,
        "remote_control": True,
        "dry_level": 2,
        "dry_level_now": 1,
        "refresh": False,
        "need_clean_filter": False,
        "water_tank_full": False,
        "door_closed": True,
        "friendly_name": "Tumble dryer",
        "icon": "mdi:tumble-dryer",
    }


async def test_cycle_sensor_idle(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(hass, aioclient_mock, load_fixture("tumble_dryer/idle.json"))

    state = hass.states.get("sensor.dryer_cycle_status")

    assert state
    assert state.state == "Hang Dry"
    assert state.attributes == {
        "friendly_name": "Dryer cycle status",
        "icon": "mdi:tumble-dryer",
    }


async def test_cycle_sensor_running(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(
        hass, aioclient_mock, load_fixture("tumble_dryer/running.json")
    )

    state = hass.states.get("sensor.dryer_cycle_status")

    assert state
    assert state.state == "Running"
    assert state.attributes == {
        "friendly_name": "Dryer cycle status",
        "icon": "mdi:tumble-dryer",
    }


async def test_cycle_sensor_pre_heating(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """When the dryer is in program phase 1 (pre-heating), sensors should stay available."""
    pre_heating_fixture = load_fixture("tumble_dryer/running.json").replace(
        '"PrPh": "2"', '"PrPh": "1"'
    )
    await init_integration(hass, aioclient_mock, pre_heating_fixture)

    state = hass.states.get("sensor.dryer_cycle_status")

    assert state
    assert state.state == "Pre-heating"
    assert state.attributes == {
        "friendly_name": "Dryer cycle status",
        "icon": "mdi:tumble-dryer",
    }


async def test_remaining_time_sensor_idle(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(hass, aioclient_mock, load_fixture("tumble_dryer/idle.json"))

    state = hass.states.get("sensor.dryer_cycle_remaining_time")

    assert state
    assert state.state == "0"
    assert state.attributes == {
        "device_class": "duration",
        "friendly_name": "Dryer cycle remaining time",
        "icon": "mdi:progress-clock",
        "unit_of_measurement": "min",
    }


async def test_remaining_time_sensor_running(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(
        hass, aioclient_mock, load_fixture("tumble_dryer/running.json")
    )

    state = hass.states.get("sensor.dryer_cycle_remaining_time")

    assert state
    assert state.state == "150"
    assert state.attributes == {
        "device_class": "duration",
        "friendly_name": "Dryer cycle remaining time",
        "icon": "mdi:progress-clock",
        "unit_of_measurement": "min",
    }


async def test_main_sensor_device_info(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(hass, aioclient_mock, load_fixture("tumble_dryer/idle.json"))

    entity_reg = entity_registry.async_get(hass)
    device_reg = device_registry.async_get(hass)
    entry = entity_reg.async_get("sensor.tumble_dryer")
    device = device_reg.async_get(entry.device_id)

    assert device
    assert device.manufacturer == "Candy"
    assert device.name == "Tumble dryer"
    assert device.suggested_area == "Bathroom"


async def test_sensors_device_info(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    await init_integration(hass, aioclient_mock, load_fixture("tumble_dryer/idle.json"))

    entity_reg = entity_registry.async_get(hass)
    device_reg = device_registry.async_get(hass)

    main_sensor = entity_reg.async_get("sensor.tumble_dryer")
    cycle_sensor = entity_reg.async_get("sensor.dryer_cycle_status")
    time_sensor = entity_reg.async_get("sensor.dryer_cycle_remaining_time")

    main_device = device_reg.async_get(main_sensor.device_id)
    cycle_device = device_reg.async_get(cycle_sensor.device_id)
    time_device = device_reg.async_get(time_sensor.device_id)

    assert main_device
    assert cycle_device
    assert time_device
    assert main_device == cycle_device == time_device


async def test_dry_level_and_diagnostic_sensors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test dry level and diagnostic sensors."""
    await init_integration(hass, aioclient_mock, load_fixture("tumble_dryer/idle.json"))

    dry_level_state = hass.states.get("sensor.dry_level")
    assert dry_level_state
    assert dry_level_state.state == "hang_dry"

    checkup_state = hass.states.get("sensor.check_up_state")
    assert checkup_state
    assert checkup_state.state == "Idle"


async def test_error_code_sensor_when_error_reported(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test error code sensor when an error is present."""
    fixture = load_fixture("tumble_dryer/idle.json").replace(
        '"CodiceErrore": "0"', '"CodiceErrore": "E03"'
    )
    await init_integration(hass, aioclient_mock, fixture)

    error_state = hass.states.get("sensor.dryer_error")
    assert error_state
    assert error_state.state == "E03"
