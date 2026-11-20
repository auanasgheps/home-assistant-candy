"""Unit tests for tools/appliance_manager.py."""

from __future__ import annotations

import http.client
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

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
    mock_resp.status = 200

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
