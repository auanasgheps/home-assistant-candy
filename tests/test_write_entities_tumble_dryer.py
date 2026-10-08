"""Tests for tumble dryer write entities (select/number/button) in Full Control mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.candy import CONF_KEY_USE_ENCRYPTION, DOMAIN
from custom_components.candy.const import (
    CONF_KEY_INTERFACE_TYPE,
    CONF_KEY_IS_TUMBLE_DRYER,
    CONF_KEY_MODE,
    CONF_KEY_PROGRAM_LANGUAGE,
    CONF_KEY_PROGRAMS,
    MODE_FULL_CONTROL,
    UNIQUE_ID_TUMBLE_ANTI_CREASE_BUTTON,
    UNIQUE_ID_TUMBLE_CHECKUP_BUTTON,
    UNIQUE_ID_TUMBLE_DELAY_NUMBER,
    UNIQUE_ID_TUMBLE_DRY_LEVEL_SELECT,
    UNIQUE_ID_TUMBLE_PAUSE_BUTTON,
    UNIQUE_ID_TUMBLE_PROGRAM_SELECT,
    UNIQUE_ID_TUMBLE_RESET_WARNINGS_BUTTON,
    UNIQUE_ID_TUMBLE_RESUME_BUTTON,
    UNIQUE_ID_TUMBLE_START_BUTTON,
    UNIQUE_ID_TUMBLE_STOP_BUTTON,
    UNIQUE_ID_TUMBLE_TIME_SELECT,
)

from .common import TEST_IP

_PROGRAM_COTTON = {
    "position": 1,
    "name": "COTTON",
    "default_drying_level": 3,
    "max_time_level": 120,
    "default_time_level": 60,
    "set_dry_level": 1,
    "set_time_level": 1,
    "set_rapido": 0,
    "duration": 150,
    "parameters": {
        "selector_position": 1,
    },
}

_PROGRAM_SYNTHETICS = {
    "position": 2,
    "name": "SYNTHETICS",
    "default_drying_level": 2,
    "max_time_level": 0,
    "default_time_level": 0,
    "set_dry_level": 1,
    "set_time_level": 0,
    "set_rapido": 0,
    "duration": 90,
    "parameters": {
        "selector_position": 2,
    },
}

_DRYER_PROGRAMS = [_PROGRAM_COTTON, _PROGRAM_SYNTHETICS]

_IDLE_JSON = """{
  "statusTD": {
    "StatoWiFi": "1",
    "StatoTD": "1",
    "CodiceErrore": "0",
    "Pr": "1",
    "PrPh": "0",
    "RemTime": "150",
    "DryLev": "3",
    "Time": "0",
    "Rapido": "0",
    "Refresh": "0",
    "CleanFilter": "0",
    "WaterTankFull": "0",
    "DryingManagerLevel": "3",
    "DelVal": "0",
    "DoorState": "1",
    "RecipeId": "NULL",
    "CheckUpState": "0"
  }
}"""

_RUNNING_JSON = """{
  "statusTD": {
    "StatoWiFi": "1",
    "StatoTD": "2",
    "CodiceErrore": "0",
    "Pr": "1",
    "PrPh": "2",
    "RemTime": "100",
    "DryLev": "3",
    "Time": "0",
    "Rapido": "0",
    "Refresh": "0",
    "CleanFilter": "0",
    "WaterTankFull": "0",
    "DryingManagerLevel": "3",
    "DelVal": "0",
    "DoorState": "1",
    "RecipeId": "NULL",
    "CheckUpState": "0"
  }
}"""

_PAUSED_JSON = """{
  "statusTD": {
    "StatoWiFi": "1",
    "StatoTD": "3",
    "CodiceErrore": "0",
    "Pr": "1",
    "PrPh": "2",
    "RemTime": "100",
    "DryLev": "3",
    "Time": "0",
    "Rapido": "0",
    "Refresh": "0",
    "CleanFilter": "0",
    "WaterTankFull": "0",
    "DryingManagerLevel": "3",
    "DelVal": "0",
    "DoorState": "1",
    "RecipeId": "NULL",
    "CheckUpState": "0"
  }
}"""

_FINISHED_JSON = """{
  "statusTD": {
    "StatoWiFi": "1",
    "StatoTD": "7",
    "CodiceErrore": "0",
    "Pr": "1",
    "PrPh": "3",
    "RemTime": "0",
    "DryLev": "3",
    "Time": "0",
    "Rapido": "0",
    "Refresh": "0",
    "CleanFilter": "0",
    "WaterTankFull": "0",
    "DryingManagerLevel": "3",
    "DelVal": "0",
    "DoorState": "1",
    "RecipeId": "NULL",
    "CheckUpState": "0"
  }
}"""


async def _init_dryer_full_control(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status_json: str = _IDLE_JSON,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test-dryer-full-control",
        data={
            CONF_IP_ADDRESS: TEST_IP,
            CONF_KEY_USE_ENCRYPTION: False,
            CONF_PASSWORD: "",
            CONF_KEY_MODE: MODE_FULL_CONTROL,
            CONF_KEY_PROGRAMS: _DRYER_PROGRAMS,
            CONF_KEY_INTERFACE_TYPE: "TD_DIGIT_1",
            CONF_KEY_IS_TUMBLE_DRYER: True,
            CONF_KEY_PROGRAM_LANGUAGE: "en",
        },
    )
    aioclient_mock.get(f"http://{TEST_IP}/http-read.json?encrypted=0", text=status_json)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_dryer_select_and_number_entities_created(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test dryer select and number entities are set up with correct options."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _IDLE_JSON)
    registry = er.async_get(hass)

    program_eid = registry.async_get_entity_id(
        "select", DOMAIN, UNIQUE_ID_TUMBLE_PROGRAM_SELECT.format(entry.entry_id)
    )
    assert program_eid is not None
    p_state = hass.states.get(program_eid)
    assert p_state is not None
    assert "Cotton" in p_state.attributes["options"]
    assert "Synthetics" in p_state.attributes["options"]

    level_eid = registry.async_get_entity_id(
        "select", DOMAIN, UNIQUE_ID_TUMBLE_DRY_LEVEL_SELECT.format(entry.entry_id)
    )
    assert level_eid is not None
    l_state = hass.states.get(level_eid)
    assert l_state is not None
    assert "store_dry" in l_state.attributes["options"]

    time_eid = registry.async_get_entity_id(
        "select", DOMAIN, UNIQUE_ID_TUMBLE_TIME_SELECT.format(entry.entry_id)
    )
    assert time_eid is not None
    t_state = hass.states.get(time_eid)
    assert t_state is not None
    assert "off" in t_state.attributes["options"]
    assert "60" in t_state.attributes["options"]

    delay_eid = registry.async_get_entity_id(
        "number", DOMAIN, UNIQUE_ID_TUMBLE_DELAY_NUMBER.format(entry.entry_id)
    )
    assert delay_eid is not None
    d_state = hass.states.get(delay_eid)
    assert d_state is not None
    assert float(d_state.state) == 0.0


async def test_dryer_start_button_standard(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test pressing start button sends standard drying start command."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _IDLE_JSON)
    registry = er.async_get(hass)

    start_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_START_BUTTON.format(entry.entry_id)
    )
    assert start_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": start_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["StSt"] == "1"
    assert params["PrNm"] == "1"
    assert params["DryLev"] == "3"


async def test_dryer_start_button_timed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test pressing start button with timed drying selected sends timed command."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _IDLE_JSON)
    registry = er.async_get(hass)

    time_eid = registry.async_get_entity_id(
        "select", DOMAIN, UNIQUE_ID_TUMBLE_TIME_SELECT.format(entry.entry_id)
    )
    assert time_eid is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": time_eid, "option": "60"},
        blocking=True,
    )

    start_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_START_BUTTON.format(entry.entry_id)
    )
    assert start_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": start_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["StSt"] == "1"
    assert params["PrNm"] == "1"
    assert params["Time"] == "60"


async def test_dryer_start_button_delayed(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test pressing start button with delay sends delayed start command."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _IDLE_JSON)
    registry = er.async_get(hass)

    delay_eid = registry.async_get_entity_id(
        "number", DOMAIN, UNIQUE_ID_TUMBLE_DELAY_NUMBER.format(entry.entry_id)
    )
    assert delay_eid is not None
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": delay_eid, "value": 120},
        blocking=True,
    )

    start_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_START_BUTTON.format(entry.entry_id)
    )
    assert start_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": start_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["PrNm"] == "1"
    assert params["DryLev"] == "3"
    assert params["DelMd"] == "1"
    assert params["DelVl"] == "120"


async def test_dryer_stop_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test pressing stop button sends stop command."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _RUNNING_JSON)
    registry = er.async_get(hass)

    stop_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_STOP_BUTTON.format(entry.entry_id)
    )
    assert stop_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": stop_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["StSt"] == "0"
    assert params["DelMd"] == "0"
    assert params["PrNm"] == "1"


async def test_dryer_pause_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test pause button."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _RUNNING_JSON)
    registry = er.async_get(hass)

    pause_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_PAUSE_BUTTON.format(entry.entry_id)
    )
    assert pause_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": pause_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["SetPauseDryMgr"] == "1"


async def test_dryer_resume_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test resume button in paused state."""
    paused_entry = await _init_dryer_full_control(hass, aioclient_mock, _PAUSED_JSON)
    registry = er.async_get(hass)
    resume_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_RESUME_BUTTON.format(paused_entry.entry_id)
    )
    assert resume_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send_resume:
        await hass.services.async_call(
            "button", "press", {"entity_id": resume_eid}, blocking=True
        )

    mock_send_resume.assert_called_once()
    qs = mock_send_resume.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["SetRestartDryMgr"] == "1"


async def test_dryer_anti_crease_cancel_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test anti-crease cancel button sends DontTumbling=1."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _FINISHED_JSON)
    registry = er.async_get(hass)

    cancel_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_ANTI_CREASE_BUTTON.format(entry.entry_id)
    )
    assert cancel_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": cancel_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["DontTumbling"] == "1"


async def test_dryer_checkup_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test check-up button sends CheckUpState=1."""
    entry = await _init_dryer_full_control(hass, aioclient_mock, _IDLE_JSON)
    registry = er.async_get(hass)

    checkup_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_CHECKUP_BUTTON.format(entry.entry_id)
    )
    assert checkup_eid is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": checkup_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["CheckUpState"] == "1"


async def test_dryer_reset_warnings_button(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test reset warnings button sends ResetWarnings=1 when problem flags are active."""
    warning_json = _IDLE_JSON.replace('"CleanFilter": "0"', '"CleanFilter": "1"')
    entry = await _init_dryer_full_control(hass, aioclient_mock, warning_json)
    registry = er.async_get(hass)

    reset_eid = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_TUMBLE_RESET_WARNINGS_BUTTON.format(entry.entry_id)
    )
    assert reset_eid is not None
    assert hass.states.get(reset_eid).state != "unavailable"

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": reset_eid}, blocking=True
        )

    mock_send.assert_called_once()
    qs = mock_send.call_args[0][0]
    params = {k: v[0] for k, v in parse_qs(qs).items()}
    assert params["Write"] == "1"
    assert params["ResetWarnings"] == "1"
