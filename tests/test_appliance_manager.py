"""Unit tests for tools/appliance_manager.py."""

from __future__ import annotations

import argparse
import http.client
import io
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.error

import pytest

# Ensure tools directory is in sys.path
sys.path.insert(0, "tools")
import appliance_manager as mgr  # noqa: E402

import custom_components.candy  # noqa: F401


def test_xor_cryptography_roundtrip() -> None:
    """Test XOR encryption and decryption roundtrip."""
    key = "ABCDEF0123456789"
    message = (
        "NTW_MODE=3&SSID=HomeNetwork&PASSWORD=Secret123&ENCRYPT_KEY=NewKey1234567890"
    )

    encrypted_hex = mgr.xor_encrypt_hex(message, key)
    assert isinstance(encrypted_hex, str)
    assert encrypted_hex == encrypted_hex.upper()

    decrypted = mgr.xor_decrypt_hex(encrypted_hex, key)
    assert decrypted == message


def test_xor_with_empty_key_raises_error() -> None:
    """Test that empty key raises ValueError."""
    with pytest.raises(ValueError, match="Encryption key cannot be empty"):
        mgr.xor_with_key(b"data", b"")


def test_clean_ssid() -> None:
    """Test clean_ssid quote removal and space replacement."""
    assert mgr.clean_ssid('"My SSID"', False) == "My SSID"
    assert mgr.clean_ssid('"My SSID"', True) == "My$SSID"
    assert mgr.clean_ssid("SimpleSSID", True) == "SimpleSSID"


def test_derive_softap_key_bianca_axi() -> None:
    """Test key derivation for Bianca / AXI models (first 8 chars repeated)."""
    ssid = "Candy_Lavatrice_123456"
    key = mgr.derive_softap_key_for_bianca_axi(ssid)
    assert len(key) == 16
    assert key == "Candy_LaCandy_La"


def test_derive_softap_key_standard() -> None:
    """Test key derivation for standard / DualTech models (last 8 chars repeated)."""
    ssid = "Candy_Lavatrice_123456"
    key = mgr.derive_softap_key_for_standard(ssid)
    assert len(key) == 16
    assert key == "e_123456e_123456"


def test_derive_softap_key_too_short_raises_error() -> None:
    """Test that SSID shorter than 8 chars raises ValueError."""
    with pytest.raises(ValueError, match="too short"):
        mgr.derive_softap_key_for_bianca_axi("Candy")

    with pytest.raises(ValueError, match="too short"):
        mgr.derive_softap_key_for_standard("Candy")


def test_generate_random_key() -> None:
    """Test random encryption key generation."""
    key = mgr.generate_random_key(16)
    assert len(key) == 16
    assert key.isalnum()


def test_crc16_iso13239() -> None:
    """Test ISO 13239 CRC-16 computation."""
    data = b"TEST_PAYLOAD"
    crc = mgr.calculate_crc16_iso13239(data)
    assert isinstance(crc, int)
    assert 0 <= crc <= 0xFFFF


def test_build_ble_enrollment_packet() -> None:
    """Test framed BLE enrollment packet construction."""
    ssid = "HomeWiFi"
    password = "SecretPassword"
    security = 3
    key = "1234567890123456"

    packet = mgr.build_ble_enrollment_packet(ssid, password, security, key)
    assert len(packet) > 5
    # Magic byte
    assert packet[0] == mgr.BLE_MAGIC_BYTE  # 0xA5
    # Total length
    assert packet[1] == len(packet)
    # Action code
    assert packet[2] == mgr.BLE_ACTION_ENROLL  # 0x16

    # Verify payload format in slice
    payload_slice = packet[3:-2].decode("utf-8")
    assert f"NTW_MODE={security}" in payload_slice
    assert f"SSID={ssid}" in payload_slice
    assert f"PASSWORD={password}" in payload_slice
    assert f"ENCRYPT_KEY={key}" in payload_slice

    # Verify CRC matches
    computed_crc = mgr.calculate_crc16_iso13239(packet[:-2])
    packet_crc = (packet[-2] << 8) | packet[-1]
    assert packet_crc == computed_crc


def test_extract_json_from_response_with_padding() -> None:
    """Test extracting JSON from response with trailing null bytes and extra data."""
    raw = ' \x00 {"response":"SUCCESS"} \x00\x00\x00extra_garbage'
    parsed = mgr.extract_json_from_response(raw)
    assert parsed.get("response") == "SUCCESS"


def test_cloud_authenticate_success() -> None:
    """Test cloud authentication via CIAM PKCE flow."""
    mock_auth_resp = {"session_id": "test_session_123"}
    mock_token_resp = {
        "tokens": {
            "id_token": "id_token_abc",
            "cognito_token": "cognito_xyz",
        }
    }

    with patch(
        "appliance_manager.cloud_http_request",
        side_effect=[mock_auth_resp, mock_token_resp],
    ):
        tokens = mgr.cloud_authenticate("user@example.com", "pass123", 10.0)
        assert tokens["id_token"] == "id_token_abc"
        assert tokens["cognito_token"] == "cognito_xyz"


def test_cloud_authenticate_failure() -> None:
    """Test cloud authentication failure raises CloudAuthError."""
    with (
        patch(
            "appliance_manager.cloud_http_request",
            return_value={"error": "invalid_credentials"},
        ),
        pytest.raises(mgr.CloudAuthError),
    ):
        mgr.cloud_authenticate("user@example.com", "pass123", 10.0)


def test_cloud_list_appliances() -> None:
    """Test listing appliances from cloud."""
    mock_list = [
        {"appliance": {"id": 101, "mac_address": "AA:BB:CC:DD:EE:FF"}},
        {"appliance": {"id": 102, "mac_address": "11:22:33:44:55:66"}},
    ]
    tokens = {"id_token": "token1", "cognito_token": "token2"}

    with patch("appliance_manager.cloud_http_request", return_value=mock_list):
        appliances = mgr.cloud_list_appliances(tokens, 10.0)
        assert len(appliances) == 2
        assert appliances[0]["appliance"]["id"] == 101


def test_cloud_add_appliance() -> None:
    """Test registering an appliance on cloud."""
    mock_resp = {"appliance": {"id": 201, "mac_address": "aabbccddeeff"}}
    tokens = {"id_token": "token1", "cognito_token": "token2"}

    with patch(
        "appliance_manager.cloud_http_request", return_value=mock_resp
    ) as mock_req:
        result = mgr.cloud_add_appliance(
            tokens,
            "1234567890123456",
            "key1234567890123",
            "HomeSSID",
            "AA:BB:CC:DD:EE:FF",
            3,
            "2026-01-01",
            10.0,
        )
        assert result["appliance"]["id"] == 201
        assert mock_req.call_count == 1
        call_args = mock_req.call_args[0]
        data_sent = json.loads(call_args[3].decode("utf-8"))
        assert data_sent["appliance"]["mac_address"] == "aabbccddeeff"
        assert data_sent["appliance"]["purchase_date"] == "2026-01-01"


def test_cloud_delete_appliance() -> None:
    """Test deleting an appliance from cloud."""
    tokens = {"id_token": "token1", "cognito_token": "token2"}
    mock_resp = MagicMock()
    mock_resp.read.return_value = b""

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        success = mgr.cloud_delete_appliance(tokens, "101", 10.0)
        assert success is True


def test_provision_softap_encrypted_success() -> None:
    """Test SoftAP provisioning success path with encrypted roundtrip."""
    new_key = "NEWKEY1234567890"
    softap_ssid = "Candy_Lavatrice_4455"
    target_ssid = "MyHomeWiFi"
    target_pass = "MySecret123"

    response_json = '{"response":"SUCCESS"}'
    encrypted_resp_hex = mgr.xor_encrypt_hex(response_json, new_key)

    mock_resp = MagicMock()
    mock_resp.read.return_value = encrypted_resp_hex.encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        result = mgr.provision_softap(
            "192.168.0.1",
            80,
            softap_ssid,
            False,
            True,
            target_ssid,
            target_pass,
            3,
            new_key,
            5.0,
        )
        assert result.get("response") == "SUCCESS"
        assert mock_url.call_count == 1


def test_provision_softap_unencrypted_success() -> None:
    """Test SoftAP provisioning in plaintext unencrypted mode."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"response":"SUCCESS"}'

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        result = mgr.provision_softap(
            "192.168.0.1",
            80,
            "Candy_Lavatrice_4455",
            False,
            False,
            "MyHomeWiFi",
            "MySecret123",
            3,
            "KEY1234567890123",
            5.0,
        )
        assert result.get("response") == "SUCCESS"
        # Verify query string had encrypted=0
        req = mock_url.call_args[0][0]
        assert "encrypted=0" in req.full_url


def test_provision_softap_reboot_disconnect_handled() -> None:
    """Test SoftAP socket disconnect on firmware reboot is handled gracefully."""
    with patch(
        "urllib.request.urlopen",
        side_effect=http.client.RemoteDisconnected("Remote end closed connection"),
    ):
        result = mgr.provision_softap(
            "192.168.0.1",
            80,
            "Candy_Lavatrice_4455",
            False,
            True,
            "MyHomeWiFi",
            "MySecret123",
            3,
            "KEY1234567890123",
            5.0,
        )
        assert result.get("response") == "SUCCESS"
        assert result.get("rebooted") is True


def test_provision_softap_rejected_raises_error() -> None:
    """Test SoftAP provisioning raises SoftAPConfigError if appliance rejects."""
    new_key = "NEWKEY1234567890"
    response_json = '{"response":"BAD REQUEST"}'
    encrypted_resp_hex = mgr.xor_encrypt_hex(response_json, new_key)

    mock_resp = MagicMock()
    mock_resp.read.return_value = encrypted_resp_hex.encode("utf-8")

    with (
        patch("urllib.request.urlopen") as mock_url,
        pytest.raises(mgr.SoftAPConfigError, match="rejected configuration"),
    ):
        mock_url.return_value.__enter__.return_value = mock_resp
        mgr.provision_softap(
            "192.168.0.1",
            80,
            "Candy_Lavatrice_4455",
            False,
            True,
            "MyHomeWiFi",
            "MySecret123",
            3,
            new_key,
            5.0,
        )


@pytest.mark.asyncio
async def test_provision_ble_success() -> None:
    """Test BLE provisioning with MAC reading and packet dispatch."""
    mock_client = AsyncMock()
    mock_client.is_connected = True
    mock_client.read_gatt_char.return_value = bytes(
        [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]
    )

    mock_bleak = MagicMock()
    mock_bleak.BleakClient.return_value.__aenter__.return_value = mock_client

    with patch.dict(sys.modules, {"bleak": mock_bleak}):
        result = await mgr.provision_ble(
            "11:22:33:44:55:66",
            "MyHomeWiFi",
            "SecretPass",
            3,
            "KEY1234567890123",
            10.0,
        )
        assert result.get("response") == "SUCCESS"
        assert result.get("mac_address") == "aa:bb:cc:dd:ee:ff"
        assert mock_client.write_gatt_char.call_count == 1


@pytest.mark.asyncio
async def test_scan_for_candy_ble_devices() -> None:
    """Test BLE scanning filtering for Candy/Hoover appliances."""
    dev1 = MagicMock(address="11:22:33:44:55:66", name="Candy_Washer")
    adv1 = MagicMock(
        local_name="Candy_Washer",
        service_uuids=[mgr.BLE_SERVICE_UUID],
        manufacturer_data={741: b"\x01"},
    )

    dev2 = MagicMock(address="AA:BB:CC:DD:EE:FF", name="OtherDevice")
    adv2 = MagicMock(
        local_name="OtherDevice",
        service_uuids=["0000180d-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={},
    )

    mock_bleak = MagicMock()
    mock_bleak.BleakScanner.discover = AsyncMock(
        return_value={
            "dev1": (dev1, adv1),
            "dev2": (dev2, adv2),
        }
    )

    with patch.dict(sys.modules, {"bleak": mock_bleak}):
        found = await mgr.scan_for_candy_ble_devices(5.0)
        assert len(found) == 1
        assert found[0][0] == "11:22:33:44:55:66"
        assert "Candy" in found[0][1]


def test_parser_has_provision_ble_command() -> None:
    """Test build_parser includes provision-ble subcommand and flags."""
    parser = mgr.build_parser()
    args = parser.parse_args(
        [
            "provision-ble",
            "--device-address",
            "AA:BB:CC:DD:EE:FF",
            "--target-ssid",
            "HomeWiFi",
            "--target-password",
            "SecretPass",
        ]
    )
    assert args.command == "provision-ble"
    assert args.device_address == "AA:BB:CC:DD:EE:FF"
    assert args.target_ssid == "HomeWiFi"
    assert args.target_password == "SecretPass"


def test_parser_softap_unencrypted_flag() -> None:
    """Test build_parser includes --unencrypted flag for provision-softap."""
    parser = mgr.build_parser()
    args = parser.parse_args(
        [
            "provision-softap",
            "--softap-ssid",
            "Candy_Washer_1234",
            "--target-ssid",
            "HomeWiFi",
            "--unencrypted",
        ]
    )
    assert args.command == "provision-softap"
    assert args.unencrypted is True


def test_validate_encryption_key() -> None:
    """Test validation of 16-character alphanumeric encryption keys."""
    assert mgr.validate_encryption_key("1234567890ABCDEF") == "1234567890ABCDEF"
    assert mgr.validate_encryption_key("  abcdef1234567890  ") == "abcdef1234567890"

    with pytest.raises(ValueError, match="must be exactly 16 alphanumeric characters"):
        mgr.validate_encryption_key("short")

    with pytest.raises(ValueError, match="must be exactly 16 alphanumeric characters"):
        mgr.validate_encryption_key("toolongkey1234567890123")

    with pytest.raises(ValueError, match="must be exactly 16 alphanumeric characters"):
        mgr.validate_encryption_key("1234567890!@#$%^")


def test_validate_serial() -> None:
    """Test validation and normalization of 16-digit serial numbers."""
    assert mgr.validate_serial("3100876543210987") == "3100876543210987"
    assert mgr.validate_serial("3100-8765-4321-0987") == "3100876543210987"
    assert mgr.validate_serial(" 3100 8765 4321 0987 ") == "3100876543210987"

    with pytest.raises(ValueError, match="must be exactly 16 numeric digits"):
        mgr.validate_serial("12345")

    with pytest.raises(ValueError, match="must be exactly 16 numeric digits"):
        mgr.validate_serial("310087654321098A")


def test_validate_mac() -> None:
    """Test validation and normalization of 6-byte MAC addresses."""
    assert mgr.validate_mac("AA:BB:CC:DD:EE:FF") == "aabbccddeeff"
    assert mgr.validate_mac("aa-bb-cc-dd-ee-ff") == "aabbccddeeff"
    assert mgr.validate_mac("aabbccddeeff") == "aabbccddeeff"

    with pytest.raises(ValueError, match="must be 12 hexadecimal characters"):
        mgr.validate_mac("invalid_mac")

    with pytest.raises(ValueError, match="must be 12 hexadecimal characters"):
        mgr.validate_mac("AA:BB:CC:DD:EE")


def test_validate_security_mode() -> None:
    """Test validation of Wi-Fi security modes."""
    assert mgr.validate_security_mode(0) == 0
    assert mgr.validate_security_mode(2) == 2
    assert mgr.validate_security_mode(3) == 3

    with pytest.raises(ValueError, match="Security mode must be 0"):
        mgr.validate_security_mode(1)


def test_cloud_http_request_behaviors() -> None:
    """Test cloud_http_request handling of empty bodies, non-JSON text, and HTTP errors."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b""
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        result = mgr.cloud_http_request("https://test.com", "GET", None, None, 5.0)
        assert result == {}

    mock_resp.read.return_value = b"NON_JSON_RESPONSE"
    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        result = mgr.cloud_http_request("https://test.com", "GET", None, None, 5.0)
        assert result == {"raw": "NON_JSON_RESPONSE"}

    http_err = urllib.error.HTTPError(
        "https://test.com",
        401,
        "Unauthorized",
        {},
        io.BytesIO(b"Invalid token"),  # type: ignore[arg-type]
    )
    with (
        patch("urllib.request.urlopen", side_effect=http_err),
        pytest.raises(mgr.CloudApiError, match="HTTP 401"),
    ):
        mgr.cloud_http_request("https://test.com", "GET", None, None, 5.0)

    with (
        patch("urllib.request.urlopen", side_effect=OSError("Network unreachable")),
        pytest.raises(mgr.CloudApiError, match="Network error"),
    ):
        mgr.cloud_http_request("https://test.com", "GET", None, None, 5.0)


def test_cloud_list_appliances_invalid_format() -> None:
    """Test cloud_list_appliances raises CloudApiError on unexpected format."""
    tokens = {"id_token": "token1", "cognito_token": "token2"}
    with (
        patch(
            "appliance_manager.cloud_http_request", return_value={"unexpected": "dict"}
        ),
        pytest.raises(mgr.CloudApiError, match="Unexpected response format"),
    ):
        mgr.cloud_list_appliances(tokens, 5.0)


def test_cloud_add_appliance_invalid_format() -> None:
    """Test cloud_add_appliance raises CloudApiError when cloud returns non-dict."""
    tokens = {"id_token": "token1", "cognito_token": "token2"}
    with (
        patch("appliance_manager.cloud_http_request", return_value="string_response"),
        pytest.raises(mgr.CloudApiError, match="Unexpected response format"),
    ):
        mgr.cloud_add_appliance(
            tokens,
            "1234567890123456",
            "key1234567890123",
            "HomeSSID",
            "AA:BB:CC:DD:EE:FF",
            3,
            None,
            5.0,
        )


def test_extract_json_from_response_invalid() -> None:
    """Test extract_json_from_response raises SoftAPConfigError on non-dict JSON or invalid text."""
    with pytest.raises(mgr.SoftAPConfigError, match="Expected JSON object"):
        mgr.extract_json_from_response("[1, 2, 3]")

    with pytest.raises(mgr.SoftAPConfigError, match="Failed to parse JSON response"):
        mgr.extract_json_from_response("not a json at all")


def test_provision_softap_urlerror_reboot_disconnect() -> None:
    """Test provision_softap treats URLError wrapping connection reset as successful reboot."""
    url_err = urllib.error.URLError(ConnectionResetError("Connection reset by peer"))
    with patch("urllib.request.urlopen", side_effect=url_err):
        result = mgr.provision_softap(
            "192.168.0.1",
            80,
            "Candy_Lavatrice_4455",
            False,
            True,
            "MyHomeWiFi",
            "MySecret123",
            3,
            "KEY1234567890123",
            5.0,
        )
        assert result.get("response") == "SUCCESS"
        assert result.get("rebooted") is True


def test_provision_softap_urlerror_unhandled_raises() -> None:
    """Test provision_softap raises SoftAPConfigError on arbitrary URLError."""
    url_err = urllib.error.URLError("No route to host")
    with (
        patch("urllib.request.urlopen", side_effect=url_err),
        pytest.raises(mgr.SoftAPConfigError, match="network communication error"),
    ):
        mgr.provision_softap(
            "192.168.0.1",
            80,
            "Candy_Lavatrice_4455",
            False,
            True,
            "MyHomeWiFi",
            "MySecret123",
            3,
            "KEY1234567890123",
            5.0,
        )


def test_provision_softap_httperror_raises() -> None:
    """Test provision_softap raises SoftAPConfigError on HTTP error status."""
    http_err = urllib.error.HTTPError(
        "http://192.168.0.1/http-config.json",
        500,
        "Internal Server Error",
        {},
        io.BytesIO(b"Failed"),  # type: ignore[arg-type]
    )
    with (
        patch("urllib.request.urlopen", side_effect=http_err),
        pytest.raises(mgr.SoftAPConfigError, match="HTTP 500"),
    ):
        mgr.provision_softap(
            "192.168.0.1",
            80,
            "Candy_Lavatrice_4455",
            False,
            True,
            "MyHomeWiFi",
            "MySecret123",
            3,
            "KEY1234567890123",
            5.0,
        )


def test_provision_softap_bianca_axi() -> None:
    """Test SoftAP provisioning with Bianca / AXI key derivation."""
    new_key = "NEWKEY1234567890"
    softap_ssid = "Candy_Bianca_998877"
    response_json = '{"response":"SUCCESS"}'
    encrypted_resp_hex = mgr.xor_encrypt_hex(response_json, new_key)

    mock_resp = MagicMock()
    mock_resp.read.return_value = encrypted_resp_hex.encode("utf-8")

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        result = mgr.provision_softap(
            "192.168.0.1",
            80,
            softap_ssid,
            True,
            True,
            "MyWiFi",
            "Pass",
            3,
            new_key,
            5.0,
        )
        assert result.get("response") == "SUCCESS"


def test_provision_softap_spaces_in_ssid_unencrypted() -> None:
    """Test SoftAP unencrypted mode URL-encodes SSIDs containing spaces."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"response":"SUCCESS"}'

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value.__enter__.return_value = mock_resp
        mgr.provision_softap(
            "192.168.0.1",
            80,
            "Candy_Lavatrice_4455",
            False,
            False,
            "Home Network With Spaces",
            "MySecret123",
            3,
            "KEY1234567890123",
            5.0,
        )
        req = mock_url.call_args[0][0]
        assert "Home%20Network%20With%20Spaces" in req.full_url
        assert " " not in req.full_url


@pytest.mark.asyncio
async def test_provision_ble_not_connected() -> None:
    """Test provision_ble raises BLEConfigError when device fails to connect."""
    mock_client = AsyncMock()
    mock_client.is_connected = False
    mock_bleak = MagicMock()
    mock_bleak.BleakClient.return_value.__aenter__.return_value = mock_client

    with (
        patch.dict(sys.modules, {"bleak": mock_bleak}),
        pytest.raises(mgr.BLEConfigError, match="Failed to connect"),
    ):
        await mgr.provision_ble(
            "11:22:33:44:55:66",
            "HomeWiFi",
            "Secret",
            3,
            "KEY1234567890123",
            5.0,
        )


@pytest.mark.asyncio
async def test_provision_ble_no_bleak() -> None:
    """Test provision_ble raises BLEConfigError when bleak is not installed."""
    with (
        patch.dict(sys.modules, {"bleak": None}),
        pytest.raises(mgr.BLEConfigError, match="package is required"),
    ):
        await mgr.provision_ble(
            "11:22:33:44:55:66",
            "HomeWiFi",
            "Secret",
            3,
            "KEY1234567890123",
            5.0,
        )


@pytest.mark.asyncio
async def test_scan_for_candy_ble_devices_no_bleak() -> None:
    """Test scan_for_candy_ble_devices raises BLEConfigError when bleak is not installed."""
    with (
        patch.dict(sys.modules, {"bleak": None}),
        pytest.raises(mgr.BLEConfigError, match="package is required"),
    ):
        await mgr.scan_for_candy_ble_devices(5.0)


def test_build_ble_enrollment_packet_oversized() -> None:
    """Test build_ble_enrollment_packet raises ValueError when payload exceeds 255 bytes."""
    huge_ssid = "A" * 260
    with pytest.raises(ValueError, match="exceeds single-byte capacity"):
        mgr.build_ble_enrollment_packet(huge_ssid, "pass", 3, "KEY1234567890123")


def test_handle_cloud_list(capsys: pytest.CaptureFixture) -> None:
    """Test CLI handle_cloud_list outputs table with key and interface type."""
    mock_appliances = [
        {
            "appliance": {
                "id": "99",
                "mac_address": "aabbccddeeff",
                "appliance_type": "washer",
                "encryption_key": "KEY1234567890123",
                "additional_info": {"interface_type": "RAPIDO_4DIG"},
                "appliance_model": "RO148",
            }
        }
    ]
    with (
        patch("appliance_manager.cloud_authenticate", return_value={"id_token": "t"}),
        patch("appliance_manager.cloud_list_appliances", return_value=mock_appliances),
    ):
        args = argparse.Namespace(email="user@test.com", password="pwd", timeout=5.0)
        mgr.handle_cloud_list(args)

    out = capsys.readouterr().out
    assert "Found 1 appliance(s):" in out
    assert "aabbccddeeff" in out
    assert "KEY1234567890123" in out
    assert "RAPIDO_4DIG" in out


def test_handle_cloud_add(capsys: pytest.CaptureFixture) -> None:
    """Test CLI handle_cloud_add invokes registration successfully."""
    with (
        patch("appliance_manager.cloud_authenticate", return_value={"id_token": "t"}),
        patch(
            "appliance_manager.cloud_add_appliance",
            return_value={"appliance": {"id": 10}},
        ),
    ):
        args = argparse.Namespace(
            email="user@test.com",
            password="pwd",
            serial="3100876543210987",
            mac="AA:BB:CC:DD:EE:FF",
            key="KEY1234567890123",
            ssid="HomeNet",
            security=3,
            purchase_date="2026-01-01",
            timeout=5.0,
        )
        mgr.handle_cloud_add(args)

    out = capsys.readouterr().out
    assert "successfully registered" in out


def test_handle_cloud_remove_with_yes(capsys: pytest.CaptureFixture) -> None:
    """Test CLI handle_cloud_remove with --yes flag."""
    with (
        patch("appliance_manager.cloud_authenticate", return_value={"id_token": "t"}),
        patch("appliance_manager.cloud_delete_appliance", return_value=True),
    ):
        args = argparse.Namespace(
            email="user@test.com",
            password="pwd",
            id="123",
            yes=True,
            timeout=5.0,
        )
        mgr.handle_cloud_remove(args)

    out = capsys.readouterr().out
    assert "Appliance 123 removed successfully." in out


def test_handle_cloud_remove_cancelled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test CLI handle_cloud_remove cancellation on user prompt."""
    monkeypatch.setattr("builtins.input", lambda _: "n")
    args = argparse.Namespace(
        email="user@test.com",
        password="pwd",
        id="123",
        yes=False,
        timeout=5.0,
    )
    mgr.handle_cloud_remove(args)
    out = capsys.readouterr().out
    assert "Deletion cancelled." in out


def test_handle_provision_softap_cli(capsys: pytest.CaptureFixture) -> None:
    """Test CLI handle_provision_softap executes and prints success."""
    with patch(
        "appliance_manager.provision_softap",
        return_value={"response": "SUCCESS"},
    ):
        args = argparse.Namespace(
            softap_ip="192.168.0.1",
            port=80,
            softap_ssid="Candy_Lavatrice_123456",
            target_ssid="HomeNet",
            target_password="secret_password",
            security=3,
            key="KEY1234567890123",
            bianca_axi=False,
            unencrypted=False,
            timeout=5.0,
        )
        mgr.handle_provision_softap(args)

    out = capsys.readouterr().out
    assert "SUCCESS! Appliance acknowledged Wi-Fi configuration." in out


def test_handle_provision_ble_cli_direct(capsys: pytest.CaptureFixture) -> None:
    """Test CLI handle_provision_ble with explicit address."""
    with patch(
        "appliance_manager.provision_ble",
        new=AsyncMock(
            return_value={
                "response": "SUCCESS",
                "mac_address": "aa:bb:cc:dd:ee:ff",
            }
        ),
    ):
        args = argparse.Namespace(
            device_address="11:22:33:44:55:66",
            target_ssid="HomeNet",
            target_password="secret_password",
            security=3,
            key="KEY1234567890123",
            timeout=5.0,
        )
        mgr.handle_provision_ble(args)

    out = capsys.readouterr().out
    assert "SUCCESS! Appliance configured over BLE." in out
    assert "aa:bb:cc:dd:ee:ff" in out


def test_handle_provision_ble_cli_scan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test CLI handle_provision_ble with discovery and selection."""
    monkeypatch.setattr("builtins.input", lambda _: "1")
    with (
        patch(
            "appliance_manager.scan_for_candy_ble_devices",
            new=AsyncMock(return_value=[("11:22:33:44:55:66", "Candy Washer")]),
        ),
        patch(
            "appliance_manager.provision_ble",
            new=AsyncMock(return_value={"response": "SUCCESS"}),
        ),
    ):
        args = argparse.Namespace(
            device_address=None,
            target_ssid="HomeNet",
            target_password="secret_password",
            security=3,
            key="KEY1234567890123",
            timeout=5.0,
        )
        mgr.handle_provision_ble(args)

    out = capsys.readouterr().out
    assert "SUCCESS! Appliance configured over BLE." in out


def test_handle_wizard_softap(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test interactive wizard with SoftAP choice."""
    inputs = iter(
        [
            "",  # Step 1: Press enter
            "1",  # Step 2: SoftAP mode
            "MyHomeNet",  # target SSID
            "Candy_Lavatrice_4455",  # softap SSID
            "n",  # is_bianca
            "n",  # unencrypted
            "",  # press enter when connected
            "n",  # sync cloud
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _: "mypassword")

    with patch(
        "appliance_manager.provision_softap",
        return_value={"response": "SUCCESS"},
    ):
        args = argparse.Namespace(timeout=5.0)
        mgr.handle_wizard(args)

    out = capsys.readouterr().out
    assert "PROVISIONING SUCCESSFUL!" in out
    assert "Wizard complete!" in out


def test_handle_wizard_ble(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test interactive wizard with BLE choice."""
    inputs = iter(
        [
            "",  # Step 1: Press enter
            "2",  # Step 2: BLE mode
            "MyHomeNet",  # target SSID
            "1",  # select appliance 1
            "n",  # sync cloud
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _: "mypassword")

    with (
        patch(
            "appliance_manager.scan_for_candy_ble_devices",
            new=AsyncMock(return_value=[("11:22:33:44:55:66", "Candy Washer")]),
        ),
        patch(
            "appliance_manager.provision_ble",
            new=AsyncMock(
                return_value={
                    "response": "SUCCESS",
                    "mac_address": "11:22:33:44:55:66",
                }
            ),
        ),
    ):
        args = argparse.Namespace(timeout=5.0)
        mgr.handle_wizard(args)

    out = capsys.readouterr().out
    assert "BLE PROVISIONING SUCCESSFUL!" in out
    assert "Wizard complete!" in out


def test_handle_wizard_invalid_choice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Test interactive wizard aborts cleanly on invalid choice."""
    inputs = iter(
        [
            "",  # Step 1: Press enter
            "99",  # Step 2: Invalid
            "MyHomeNet",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _: "pass")

    args = argparse.Namespace(timeout=5.0)
    mgr.handle_wizard(args)
    out = capsys.readouterr().out
    assert "Invalid choice, exiting." in out


def test_main_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main entry point handles normal execution and exceptions cleanly."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "appliance_manager.py",
            "provision-softap",
            "--softap-ssid",
            "Candy_Lavatrice_4455",
            "--target-ssid",
            "HomeNet",
            "--target-password",
            "pwd",
            "--key",
            "KEY1234567890123",
        ],
    )
    with patch(
        "appliance_manager.provision_softap",
        return_value={"response": "SUCCESS"},
    ):
        mgr.main()

    # Test ProvisioningError caught
    with (
        patch(
            "appliance_manager.provision_softap",
            side_effect=mgr.SoftAPConfigError("Simulated error"),
        ),
        pytest.raises(SystemExit) as excinfo,
    ):
        mgr.main()
    assert excinfo.value.code == 1

    # Test KeyboardInterrupt caught
    with (
        patch(
            "appliance_manager.provision_softap",
            side_effect=KeyboardInterrupt(),
        ),
        pytest.raises(SystemExit) as excinfo,
    ):
        mgr.main()
    assert excinfo.value.code == 130
