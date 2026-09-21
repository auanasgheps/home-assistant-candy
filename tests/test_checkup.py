"""Tests for the self check-up feature."""

from __future__ import annotations

import contextlib
import copy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.candy import CONF_KEY_USE_ENCRYPTION, DOMAIN
from custom_components.candy.button import _should_send_checkup
from custom_components.candy.client.model import CheckUpResult
from custom_components.candy.const import (
    CHECKUP_SCHEDULE_EVERY_CYCLE,
    CHECKUP_SCHEDULE_MONTHLY,
    CHECKUP_SCHEDULE_WEEKLY,
    CONF_KEY_CHECKUP_ENABLED,
    CONF_KEY_CHECKUP_LAST_DATE,
    CONF_KEY_CHECKUP_LAST_RESULT,
    CONF_KEY_CHECKUP_SCHEDULE,
    CONF_KEY_MODE,
    CONF_KEY_PROGRAMS,
    DATA_KEY_COORDINATOR,
    MODE_FULL_CONTROL,
    UNIQUE_ID_WASH_CHECKUP_RESULT,
    UNIQUE_ID_WASH_LAST_CHECKUP,
    UNIQUE_ID_WASH_START_BUTTON,
)

from .common import TEST_IP

# ---------------------------------------------------------------------------
# Minimal program entry (SPECIAL_39 matching Pr=1 PrCode=136)
# ---------------------------------------------------------------------------

_SPECIAL_39 = {
    "program": {
        "position": 1,
        "name": "DUAL_WM_WD_PROGRAM_NAME_SPECIAL_39",
        "command_parameters": [
            {"command_parameter": {"name": "selector_position", "validation": "1"}},
            {"command_parameter": {"name": "pr_code", "validation": "136"}},
            {"command_parameter": {"name": "maximum_temperature", "validation": "40"}},
            {"command_parameter": {"name": "default_temperature", "validation": "40"}},
            {"command_parameter": {"name": "maximum_spin_speed", "validation": "1200"}},
            {"command_parameter": {"name": "default_spin_speed", "validation": "800"}},
            {"command_parameter": {"name": "minimum_soil_level", "validation": "0"}},
            {"command_parameter": {"name": "maximum_soil_level", "validation": "0"}},
            {"command_parameter": {"name": "default_soil_level", "validation": "0"}},
            {"command_parameter": {"name": "steam", "validation": "0"}},
            {"command_parameter": {"name": "default_duration", "validation": "39"}},
            {"command_parameter": {"name": "available_options", "validation": "240"}},
        ],
    }
}

_IDLE_JSON = """{
  "statusLavatrice": {
    "WiFiStatus": "1", "Err": "0", "MachMd": "1", "Pr": "1", "PrPh": "0",
    "PrCode": "136", "SLevel": "0", "Temp": "40", "SpinSp": "8",
    "DelVal": "0", "RemTime": "0", "FillR": "0", "CheckUpState": "0"
  }
}"""

_IDLE_WITH_DIS_TEST_RES_0 = """{
  "statusLavatrice": {
    "WiFiStatus": "1", "Err": "0", "MachMd": "1", "Pr": "1", "PrPh": "0",
    "PrCode": "136", "SLevel": "0", "Temp": "40", "SpinSp": "8",
    "DelVal": "0", "RemTime": "0", "FillR": "0", "CheckUpState": "0", "DisTestRes": "0"
  }
}"""

_IDLE_WITH_DIS_TEST_RES_1 = """{
  "statusLavatrice": {
    "WiFiStatus": "1", "Err": "0", "MachMd": "1", "Pr": "1", "PrPh": "0",
    "PrCode": "136", "SLevel": "0", "Temp": "40", "SpinSp": "8",
    "DelVal": "0", "RemTime": "0", "FillR": "0", "CheckUpState": "2", "DisTestRes": "1"
  }
}"""

_IDLE_WITH_DIS_TEST_RES_2 = """{
  "statusLavatrice": {
    "WiFiStatus": "1", "Err": "0", "MachMd": "1", "Pr": "1", "PrPh": "0",
    "PrCode": "136", "SLevel": "0", "Temp": "40", "SpinSp": "8",
    "DelVal": "0", "RemTime": "0", "FillR": "0", "CheckUpState": "2", "DisTestRes": "2"
  }
}"""

_STATS_OK = (
    '{"statusCounters": {"Temp0to30": "318", "Temp40": "70", "Temp60to90": "0"}}'
)

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(**extra) -> MockConfigEntry:
    data = {
        CONF_IP_ADDRESS: TEST_IP,
        CONF_KEY_USE_ENCRYPTION: False,
        CONF_PASSWORD: "",
        CONF_KEY_MODE: MODE_FULL_CONTROL,
        CONF_KEY_PROGRAMS: [_SPECIAL_39],
    }
    data.update(extra)
    return MockConfigEntry(domain=DOMAIN, unique_id="test-checkup", data=data)


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status_json: str,
    **extra_data,
) -> MockConfigEntry:
    entry = _make_entry(**extra_data)
    aioclient_mock.get(f"http://{TEST_IP}/http-read.json?encrypted=0", text=status_json)
    aioclient_mock.get(
        f"http://{TEST_IP}/http-prepareStatistics.json?encrypted=0",
        text='{"response":"SUCCESS"}',
    )
    aioclient_mock.get(
        f"http://{TEST_IP}/http-getStatistics.json?encrypted=0",
        text=_STATS_OK,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _sensor_state(hass: HomeAssistant, entry: MockConfigEntry, uid_tpl: str):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, uid_tpl.format(entry.entry_id)
    )
    if entity_id is None:
        return None
    return hass.states.get(entity_id)


# ---------------------------------------------------------------------------
# Unit tests for _should_send_checkup
# ---------------------------------------------------------------------------


def test_checkup_disabled_returns_0():
    entry = _make_entry(**{CONF_KEY_CHECKUP_ENABLED: False})
    assert _should_send_checkup(entry, _NOW) == 0


def test_checkup_disabled_ignores_schedule():
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: False,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_EVERY_CYCLE,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 0


def test_checkup_every_cycle_returns_1():
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_EVERY_CYCLE,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


def test_checkup_every_cycle_returns_1_even_if_recently_run():
    yesterday = (_NOW - timedelta(days=1)).timestamp()
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_EVERY_CYCLE,
            CONF_KEY_CHECKUP_LAST_DATE: yesterday,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


def test_checkup_weekly_no_last_date_returns_1():
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_WEEKLY,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


def test_checkup_weekly_8_days_elapsed_returns_1():
    last = (_NOW - timedelta(days=8)).timestamp()
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_WEEKLY,
            CONF_KEY_CHECKUP_LAST_DATE: last,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


def test_checkup_weekly_3_days_elapsed_returns_0():
    last = (_NOW - timedelta(days=3)).timestamp()
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_WEEKLY,
            CONF_KEY_CHECKUP_LAST_DATE: last,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 0


def test_checkup_weekly_exactly_7_days_elapsed_returns_1():
    last = (_NOW - timedelta(days=7)).timestamp()
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_WEEKLY,
            CONF_KEY_CHECKUP_LAST_DATE: last,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


def test_checkup_monthly_no_last_date_returns_1():
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_MONTHLY,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


def test_checkup_monthly_31_days_elapsed_returns_1():
    last = (_NOW - timedelta(days=31)).timestamp()
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_MONTHLY,
            CONF_KEY_CHECKUP_LAST_DATE: last,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


def test_checkup_monthly_20_days_elapsed_returns_0():
    last = (_NOW - timedelta(days=20)).timestamp()
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_MONTHLY,
            CONF_KEY_CHECKUP_LAST_DATE: last,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 0


def test_checkup_monthly_exactly_30_days_elapsed_returns_1():
    last = (_NOW - timedelta(days=30)).timestamp()
    entry = _make_entry(
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_MONTHLY,
            CONF_KEY_CHECKUP_LAST_DATE: last,
        }
    )
    assert _should_send_checkup(entry, _NOW) == 1


# ---------------------------------------------------------------------------
# CheckUpResult model
# ---------------------------------------------------------------------------


def test_checkup_result_enum_values():
    assert CheckUpResult.NOT_RUN.code == 0
    assert CheckUpResult.OK.code == 1
    assert CheckUpResult.PROBLEM.code == 2


def test_checkup_result_from_code():
    assert CheckUpResult.from_code(0) == CheckUpResult.NOT_RUN
    assert CheckUpResult.from_code(1) == CheckUpResult.OK
    assert CheckUpResult.from_code(2) == CheckUpResult.PROBLEM


# ---------------------------------------------------------------------------
# DisTestRes transition listener — timestamp persistence
# ---------------------------------------------------------------------------


async def test_dis_test_res_transition_0_to_1_writes_result_not_date(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """DisTestRes 0->1: result is cached; date is NOT written by the listener."""
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_0,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]

    new_status = copy.copy(coordinator.data)
    new_status.dis_test_res = CheckUpResult.OK
    coordinator.async_set_updated_data(new_status)
    await hass.async_block_till_done()

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_RESULT) == CheckUpResult.OK.code
    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None


async def test_dis_test_res_transition_0_to_2_writes_result_not_date(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """DisTestRes 0->2 (problem): result is cached; date is NOT written by the listener."""
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_0,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]

    new_status = copy.copy(coordinator.data)
    new_status.dis_test_res = CheckUpResult.PROBLEM
    coordinator.async_set_updated_data(new_status)
    await hass.async_block_till_done()

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_RESULT) == CheckUpResult.PROBLEM.code
    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None


async def test_dis_test_res_stays_non_zero_no_duplicate_write(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """DisTestRes already non-zero on second update: result not overwritten; date never written."""
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_0,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]

    # First update: 0 -> 1 (listener fires, writes result)
    ok_status = copy.copy(coordinator.data)
    ok_status.dis_test_res = CheckUpResult.OK
    coordinator.async_set_updated_data(ok_status)
    await hass.async_block_till_done()

    first_result = entry.data.get(CONF_KEY_CHECKUP_LAST_RESULT)
    assert first_result == CheckUpResult.OK.code
    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None

    # Second update: still 1, no 0->non-zero transition, must NOT overwrite
    still_ok = copy.copy(coordinator.data)
    still_ok.dis_test_res = CheckUpResult.OK
    coordinator.async_set_updated_data(still_ok)
    await hass.async_block_till_done()

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_RESULT) == first_result
    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None


async def test_dis_test_res_1_to_0_no_write(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """DisTestRes 1→0 (reset/cancel): no timestamp written."""
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_1,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]

    new_status = copy.copy(coordinator.data)
    new_status.dis_test_res = CheckUpResult.NOT_RUN
    coordinator.async_set_updated_data(new_status)
    await hass.async_block_till_done()

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None


async def test_checkup_listener_not_registered_when_disabled(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """When checkup is disabled, no timestamp is ever written even on transition."""
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_0,
        **{CONF_KEY_CHECKUP_ENABLED: False},
    )
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]

    new_status = copy.copy(coordinator.data)
    new_status.dis_test_res = CheckUpResult.OK
    coordinator.async_set_updated_data(new_status)
    await hass.async_block_till_done()

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None


# ---------------------------------------------------------------------------
# Sensor registration
# ---------------------------------------------------------------------------


async def test_checkup_result_sensor_registered_when_enabled(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_1,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    state = _sensor_state(hass, entry, UNIQUE_ID_WASH_CHECKUP_RESULT)
    assert state is not None
    assert state.state == "ok"


async def test_checkup_result_sensor_not_registered_when_disabled(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_1,
        **{CONF_KEY_CHECKUP_ENABLED: False},
    )
    state = _sensor_state(hass, entry, UNIQUE_ID_WASH_CHECKUP_RESULT)
    assert state is None


async def test_checkup_result_sensor_problem(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_2,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    state = _sensor_state(hass, entry, UNIQUE_ID_WASH_CHECKUP_RESULT)
    assert state is not None
    assert state.state == "problem"


async def test_checkup_result_sensor_not_run(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_0,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    state = _sensor_state(hass, entry, UNIQUE_ID_WASH_CHECKUP_RESULT)
    assert state is not None
    assert state.state == "not_run"


async def test_last_checkup_sensor_shows_stored_timestamp(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    ts = _NOW.timestamp()
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_JSON,
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_LAST_DATE: ts,
        },
    )
    state = _sensor_state(hass, entry, UNIQUE_ID_WASH_LAST_CHECKUP)
    assert state is not None
    assert state.state not in ("unknown", "unavailable")


async def test_last_checkup_sensor_unknown_when_never_run(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_JSON,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    state = _sensor_state(hass, entry, UNIQUE_ID_WASH_LAST_CHECKUP)
    assert state is not None
    assert state.state in ("unknown", "unavailable")


# ---------------------------------------------------------------------------
# _register_checkup_listener — guard branches not covered by other tests
# ---------------------------------------------------------------------------


async def test_checkup_listener_returns_early_when_dis_test_res_none(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """Listener returns immediately when status.dis_test_res is None."""
    # Setup with machine having DisTestRes=0 so prev_result is seeded
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_WITH_DIS_TEST_RES_0,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]

    # Push a status with dis_test_res=None — listener should return at the guard
    no_dis_status = copy.copy(coordinator.data)
    no_dis_status.dis_test_res = None
    coordinator.async_set_updated_data(no_dis_status)
    await hass.async_block_till_done()

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None


async def test_checkup_listener_returns_early_when_prev_code_none(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """Listener returns early on first update after initial state had no DisTestRes."""
    # _IDLE_JSON has no DisTestRes → initial_code=None → prev_result=[None]
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_JSON,
        **{CONF_KEY_CHECKUP_ENABLED: True},
    )
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]

    # Push status WITH DisTestRes=0 — prev_code is None → returns early without writing
    first_update = copy.copy(coordinator.data)
    first_update.dis_test_res = CheckUpResult.NOT_RUN
    coordinator.async_set_updated_data(first_update)
    await hass.async_block_till_done()

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None


# ---------------------------------------------------------------------------
# WashStartButton — checkup scheduling date written at request time
# ---------------------------------------------------------------------------


async def test_start_button_weekly_no_last_date_records_checkup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """Weekly schedule, no prior date: pressing Start sends StartCheckUp=1 and records the date."""
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_JSON,
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_WEEKLY,
        },
    )
    registry = er.async_get(hass)
    start_entity_id = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_WASH_START_BUTTON.format(entry.entry_id)
    )
    assert start_entity_id is not None

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": start_entity_id}, blocking=True
        )

    query_string: str = mock_send.call_args[0][0]
    assert "StartCheckUp=1" in query_string
    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is not None


async def test_start_button_weekly_recent_date_skips_checkup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """Weekly schedule, last checkup 3 days ago: StartCheckUp=0 and date is unchanged."""
    three_days_ago = (datetime.now(UTC) - timedelta(days=3)).timestamp()
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_JSON,
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_WEEKLY,
            CONF_KEY_CHECKUP_LAST_DATE: three_days_ago,
        },
    )
    registry = er.async_get(hass)
    start_entity_id = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_WASH_START_BUTTON.format(entry.entry_id)
    )

    with patch(
        "custom_components.candy.client.CandyClient.send_command",
        new_callable=AsyncMock,
    ) as mock_send:
        await hass.services.async_call(
            "button", "press", {"entity_id": start_entity_id}, blocking=True
        )

    query_string: str = mock_send.call_args[0][0]
    assert "StartCheckUp=0" in query_string
    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) == three_days_ago


async def test_start_button_command_failure_does_not_record_checkup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
):
    """Failed start command must not advance the checkup schedule clock."""
    entry = await _setup(
        hass,
        aioclient_mock,
        _IDLE_JSON,
        **{
            CONF_KEY_CHECKUP_ENABLED: True,
            CONF_KEY_CHECKUP_SCHEDULE: CHECKUP_SCHEDULE_WEEKLY,
        },
    )
    registry = er.async_get(hass)
    start_entity_id = registry.async_get_entity_id(
        "button", DOMAIN, UNIQUE_ID_WASH_START_BUTTON.format(entry.entry_id)
    )

    with (
        patch("asyncio.sleep"),
        patch(
            "custom_components.candy.client.CandyClient.send_command",
            new_callable=AsyncMock,
            side_effect=Exception("connection refused"),
        ),
        contextlib.suppress(Exception),
    ):
        await hass.services.async_call(
            "button", "press", {"entity_id": start_entity_id}, blocking=True
        )

    assert entry.data.get(CONF_KEY_CHECKUP_LAST_DATE) is None
