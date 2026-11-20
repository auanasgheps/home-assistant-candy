#!/usr/bin/env python3
"""Candy Simply-Fi & Hoover Wizard Appliance Manager.

Authoritative CLI and library tool to provision, re-provision, and manage
the lifecycle of Candy and Hoover smart appliances without the official app.

Confirmed against decompiled APK bytecode:
- ConnectionManager.java (configureAppliance, createNewApplianceWithSerial)
- CandySecurityUtility.java (calculateEncriptionKeyForConf, xorEncrypt/Decrypt)
- EnrollApplianceBLECommand.java (BLE GATT enrollment framing)
- NFCUtility.java (CRC16 ISO 13239 implementation)
- APIAccessor.java (deleteAppliance, cloud endpoints)
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import logging
from pathlib import Path
import secrets
import string
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

LOGGER = logging.getLogger("appliance_manager")

# Protocol Constants
CIAM_BASE_URL: str = "https://api-iot.he.services"
SIMPLY_FI_BASE_URL: str = "https://simply-fi.herokuapp.com"
DEFAULT_USER_AGENT: str = "hOn/3 CFNetwork/1240.0.4 Darwin/20.6.0"

# Default SoftAP endpoint values
DEFAULT_SOFTAP_IP: str = "192.168.0.1"
DEFAULT_SOFTAP_PORT: int = 80

# BLE GATT UUIDs (Confirmed in EnrollApplianceBLECommand / CandyEnrollmentService)
BLE_SERVICE_UUID: str = "0000a002-0000-1000-8000-00805f9b34fb"
BLE_CHAR_READ_MAC: str = "0000c300-0000-1000-8000-00805f9b34fb"
BLE_CHAR_NOTIFY_STATUS: str = "0000c301-0000-1000-8000-00805f9b34fb"
BLE_CHAR_WRITE_CONFIG: str = "0000c302-0000-1000-8000-00805f9b34fb"

# BLE Packet Magic Byte and Action Code
BLE_MAGIC_BYTE: int = 0xA5
BLE_ACTION_ENROLL: int = 0x16

# Security Modes for NTW_MODE
SECURITY_MODE_OPEN: int = 0
SECURITY_MODE_WEP: int = 2
SECURITY_MODE_WPA_WPA2: int = 3


# ---------------------------------------------------------------------------
# Specific Error Classes
# ---------------------------------------------------------------------------


class ProvisioningError(Exception):
    """Base exception for provisioning failures."""


class CloudAuthError(ProvisioningError):
    """Raised when authentication against CIAM fails."""


class CloudApiError(ProvisioningError):
    """Raised when a Simply-Fi cloud API request fails."""


class SoftAPConfigError(ProvisioningError):
    """Raised when SoftAP HTTP Wi-Fi provisioning fails."""


class BLEConfigError(ProvisioningError):
    """Raised when Bluetooth Low Energy provisioning fails."""


# ---------------------------------------------------------------------------
# Cryptography & Packet Utilities
# ---------------------------------------------------------------------------


def xor_with_key(data: bytes, key: bytes) -> bytes:
    """XOR bytes with repeated key bytes."""
    key_len = len(key)
    if key_len == 0:
        raise ValueError("Encryption key cannot be empty")
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def xor_encrypt_hex(message: str, key: str) -> str:
    """Encrypt plaintext string with repeated XOR key and return uppercase hex."""
    msg_bytes = message.encode("utf-8")
    key_bytes = key.encode("utf-8")
    cipher_bytes = xor_with_key(msg_bytes, key_bytes)
    return cipher_bytes.hex().upper()


def xor_decrypt_hex(hex_str: str, key: str) -> str:
    """Decrypt uppercase hex string with repeated XOR key and return decoded string."""
    clean_hex = hex_str.strip().strip("\x00")
    raw_bytes = bytes.fromhex(clean_hex)
    key_bytes = key.encode("utf-8")
    decrypted_bytes = xor_with_key(raw_bytes, key_bytes)
    return decrypted_bytes.decode("utf-8", errors="replace")


def clean_ssid(ssid_input: str, replace_spaces: bool) -> str:
    """Sanitize SSID by stripping quotes and optionally replacing spaces with '$'.

    Confirmed via CandyStringUtility.cleanSSID in decompiled APK.
    """
    stripped = ssid_input.replace('"', "")
    if replace_spaces:
        return stripped.replace(" ", "$")
    return stripped


def derive_softap_key_for_bianca_axi(clean_ssid_str: str) -> str:
    """Derive 16-character SoftAP XOR key for Bianca / AXI models.

    Confirmed via CandySecurityUtility.getStartupKey / calculateEncriptionKeyForConf:
    First 8 characters repeated twice.
    """
    if len(clean_ssid_str) < 8:
        raise ValueError(
            f"SoftAP SSID '{clean_ssid_str}' is too short (minimum 8 characters required)"
        )
    sub = clean_ssid_str[:8]
    return sub + sub


def derive_softap_key_for_standard(clean_ssid_str: str) -> str:
    """Derive 16-character SoftAP XOR key for standard (DualTech and other) models.

    Confirmed via CandySecurityUtility.calculateEncriptionKeyForConf:
    Last 8 characters repeated twice.
    """
    if len(clean_ssid_str) < 8:
        raise ValueError(
            f"SoftAP SSID '{clean_ssid_str}' is too short (minimum 8 characters required)"
        )
    sub = clean_ssid_str[-8:]
    return sub + sub


def generate_random_key(length: int) -> str:
    """Generate a random alphanumeric encryption key.

    Confirmed via CandySecurityUtility.calculateEncriptionKey (16 alphanumeric characters).
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def calculate_crc16_iso13239(data: bytes) -> int:
    """Calculate ISO 13239 CRC-16 with polynomial 0x6363 and inverted output.

    Confirmed via NFCUtility.crc16 in decompiled APK bytecode:
    POLYNOMIAL = 25443 (0x6363), initial value 0xFFFF.
    """
    crc = 0xFFFF
    polynomial = 25443
    for byte in data:
        crc ^= byte & 0xFF
        for _ in range(8):
            if (crc & 1) != 0:
                crc = (crc >> 1) ^ polynomial
            else:
                crc = crc >> 1
    return (~crc) & 0xFFFF


def build_ble_enrollment_packet(
    ssid: str, password: str, security_mode: int, encryption_key: str
) -> bytes:
    """Construct framed BLE enrollment packet with header and ISO 13239 CRC-16.

    Confirmed via EnrollApplianceBLECommand.java:
    Byte 0: 0xA5 (Magic code)
    Byte 1: Total length (payload length + 5)
    Byte 2: 0x16 (Action code 22)
    Bytes 3..N+2: UTF-8 payload "NTW_MODE=%s&SSID=%s&PASSWORD=%s&ENCRYPT_KEY=%s"
    Bytes N+3..N+4: CRC16 big-endian
    """
    payload_str = (
        f"NTW_MODE={security_mode}&SSID={ssid}&PASSWORD={password}&ENCRYPT_KEY={encryption_key}"
    )
    payload_bytes = payload_str.encode("utf-8")
    total_len = len(payload_bytes) + 5
    if total_len > 255:
        raise ValueError(
            f"BLE payload total length {total_len} exceeds single-byte capacity (255)"
        )

    packet = bytearray()
    packet.append(BLE_MAGIC_BYTE)
    packet.append(total_len)
    packet.append(BLE_ACTION_ENROLL)
    packet.extend(payload_bytes)

    # Compute CRC over the packet bytes before appending CRC
    crc = calculate_crc16_iso13239(bytes(packet))
    packet.append((crc >> 8) & 0xFF)
    packet.append(crc & 0xFF)

    return bytes(packet)


# ---------------------------------------------------------------------------
# Cloud API Client
# ---------------------------------------------------------------------------


def base64url(data: bytes) -> str:
    """Encode bytes using URL-safe base64 without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE verifier and SHA-256 challenge pair."""
    verifier = base64url(secrets.token_bytes(64))
    challenge = base64url(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def cloud_http_request(
    url: str,
    method: str,
    headers: dict[str, str] | None,
    data: bytes | None,
    timeout_seconds: float,
) -> Any:
    """Execute HTTP request against cloud APIs with explicit parameters and error handling."""
    req_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers is not None:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        raise CloudApiError(
            f"HTTP {err.code} from {url}: {err_body[:300]}"
        ) from err
    except Exception as exc:
        raise CloudApiError(f"Network error requesting {url}: {exc}") from exc


def cloud_authenticate(email: str, password: str, timeout_seconds: float) -> dict[str, str]:
    """Authenticate against CIAM using PKCE flow and return token dictionary."""
    verifier, challenge = generate_pkce_pair()

    # Step 1: GET /ciam/authorize
    query_params = urllib.parse.urlencode({
        "username": email,
        "password": password,
        "code_challenge": challenge,
    })
    auth_url = f"{CIAM_BASE_URL}/ciam/authorize?{query_params}"
    auth_resp = cloud_http_request(auth_url, "GET", None, None, timeout_seconds)
    session_id = auth_resp.get("session_id") if isinstance(auth_resp, dict) else None
    if not session_id:
        raise CloudAuthError(f"CIAM authorize failed, response missing session_id: {auth_resp}")

    # Step 2: POST /ciam/token
    token_url = f"{CIAM_BASE_URL}/ciam/token"
    token_payload = json.dumps({"session_id": session_id, "code_verifier": verifier}).encode("utf-8")
    token_resp = cloud_http_request(
        token_url,
        "POST",
        {"Content-Type": "application/json"},
        token_payload,
        timeout_seconds,
    )
    tokens = token_resp.get("tokens") if isinstance(token_resp, dict) else None
    if not tokens or "id_token" not in tokens:
        raise CloudAuthError(f"CIAM token exchange failed: {token_resp}")

    return {
        "id_token": str(tokens["id_token"]),
        "cognito_token": str(tokens.get("cognito_token", "")),
    }


def cloud_build_headers(tokens: dict[str, str]) -> dict[str, str]:
    """Build standard authorization headers for Simply-Fi API."""
    return {
        "id-token": tokens["id_token"],
        "cognito-token": tokens["cognito_token"],
        "Authorization": f"Bearer {tokens['id_token']}",
        "Salesforce-Auth": "1",
        "Content-Type": "application/json;charset=UTF-8",
    }


def cloud_list_appliances(tokens: dict[str, str], timeout_seconds: float) -> list[dict[str, Any]]:
    """Fetch user appliances registered on the Simply-Fi cloud account."""
    url = f"{SIMPLY_FI_BASE_URL}/api/v1/appliances.json?with_hidden_programs=1"
    headers = cloud_build_headers(tokens)
    data = cloud_http_request(url, "GET", headers, None, timeout_seconds)
    if isinstance(data, list):
        return data
    raise CloudApiError(f"Unexpected response format from list appliances: {data}")


def cloud_add_appliance(
    tokens: dict[str, str],
    serial: str,
    encryption_key: str,
    ssid: str,
    mac_address: str,
    security_mode: int,
    purchase_date: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Register a new appliance on the Simply-Fi cloud account.

    Confirmed via ConnectionManager.createNewApplianceWithSerial.
    """
    url = f"{SIMPLY_FI_BASE_URL}/api/v1/appliances.json"
    headers = cloud_build_headers(tokens)

    clean_mac = mac_address.replace(":", "").replace("-", "").lower()
    appliance_data: dict[str, Any] = {
        "sixteen_digits_code": serial,
        "encryption_key": encryption_key,
        "ssid_name": ssid,
        "mac_address": clean_mac,
        "ssid_security": str(security_mode),
    }
    if purchase_date is not None:
        appliance_data["purchase_date"] = purchase_date

    payload = json.dumps({"appliance": appliance_data}).encode("utf-8")
    resp = cloud_http_request(url, "POST", headers, payload, timeout_seconds)
    if isinstance(resp, dict):
        return resp
    raise CloudApiError(f"Unexpected response format from add appliance: {resp}")


def cloud_delete_appliance(
    tokens: dict[str, str], appliance_id: str, timeout_seconds: float
) -> bool:
    """Delete an appliance from the Simply-Fi cloud account.

    Confirmed via APIAccessor.deleteAppliance (/api/v1/appliances/{id}).
    """
    url = f"{SIMPLY_FI_BASE_URL}/api/v1/appliances/{appliance_id}"
    headers = cloud_build_headers(tokens)

    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return resp.status in (200, 204)
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        raise CloudApiError(
            f"Failed to delete appliance {appliance_id} (HTTP {err.code}): {err_body[:300]}"
        ) from err
    except Exception as exc:
        raise CloudApiError(
            f"Network error deleting appliance {appliance_id}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# SoftAP Provisioning Engine
# ---------------------------------------------------------------------------


def provision_softap(
    softap_ip: str,
    port: int,
    softap_ssid: str,
    is_bianca_axi: bool,
    target_ssid: str,
    target_password: str,
    security_mode: int,
    encryption_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Push target Wi-Fi credentials to an appliance connected in SoftAP mode.

    Confirmed via ConnectionManager.configureAppliance / configureApplianceEncrypted.
    """
    # 1. Clean SSIDs and derive temporary SoftAP XOR key
    cleaned_softap_ssid = clean_ssid(softap_ssid, not is_bianca_axi)
    if is_bianca_axi:
        softap_xor_key = derive_softap_key_for_bianca_axi(cleaned_softap_ssid)
    else:
        softap_xor_key = derive_softap_key_for_standard(cleaned_softap_ssid)

    # 2. Format configuration query string in exact key order
    params_str = (
        f"NTW_MODE={security_mode}&SSID={target_ssid}&PASSWORD={target_password}&ENCRYPT_KEY={encryption_key}"
    )

    # 3. Encrypt payload with temporary SoftAP key
    encrypted_data = xor_encrypt_hex(params_str, softap_xor_key)
    request_url = (
        f"http://{softap_ip}:{port}/http-config.json?encrypted=1&data={encrypted_data}"
    )

    # 4. Dispatch HTTP GET request
    req = urllib.request.Request(
        request_url,
        headers={"User-Agent": DEFAULT_USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw_response = resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        raise SoftAPConfigError(
            f"SoftAP provisioning failed (HTTP {err.code}): {err_body[:300]}"
        ) from err
    except Exception as exc:
        raise SoftAPConfigError(f"SoftAP network communication error: {exc}") from exc

    # 5. Decrypt response using the NEWLY PROVISIONED encryption key
    # (Appliance immediately activates the new key upon receiving http-config.json)
    try:
        decrypted_response = xor_decrypt_hex(raw_response, encryption_key)
        parsed_json = json.loads(decrypted_response)
    except Exception as exc:
        # Fall back to checking if response was returned in plaintext
        try:
            parsed_json = json.loads(raw_response)
        except Exception:
            raise SoftAPConfigError(
                f"Failed to decrypt/parse SoftAP response '{raw_response}': {exc}"
            ) from exc

    # 6. Validate response
    status_response = parsed_json.get("response", "")
    if str(status_response).lower() != "success":
        raise SoftAPConfigError(
            f"Appliance rejected configuration with response: {parsed_json}"
        )

    return parsed_json


# ---------------------------------------------------------------------------
# BLE Provisioning Engine (Async with Bleak)
# ---------------------------------------------------------------------------


async def provision_ble(
    device_address: str,
    target_ssid: str,
    target_password: str,
    security_mode: int,
    encryption_key: str,
    timeout_seconds: float,
) -> bool:
    """Push target Wi-Fi credentials to a BLE-enabled appliance (RapidÓ, Bianca, AXI).

    Confirmed via EnrollApplianceBLECommand.java and wire_protocol.md.
    """
    try:
        import bleak
    except ImportError as err:
        raise BLEConfigError(
            "The 'bleak' package is required for Bluetooth Low Energy provisioning. "
            "Install it via: pip install bleak"
        ) from err

    packet = build_ble_enrollment_packet(
        target_ssid, target_password, security_mode, encryption_key
    )

    LOGGER.info("Connecting to BLE appliance at %s...", device_address)
    async with bleak.BleakClient(device_address, timeout=timeout_seconds) as client:
        if not client.is_connected:
            raise BLEConfigError(f"Failed to connect to BLE device at {device_address}")

        LOGGER.info("Connected. Writing Wi-Fi credentials to characteristic %s...", BLE_CHAR_WRITE_CONFIG)
        await client.write_gatt_char(BLE_CHAR_WRITE_CONFIG, packet, response=True)
        LOGGER.info("BLE configuration packet written successfully.")

    return True


# ---------------------------------------------------------------------------
# CLI Command Handlers
# ---------------------------------------------------------------------------


def handle_cloud_list(args: argparse.Namespace) -> None:
    """Handle 'cloud-list' CLI command."""
    email = args.email or input("Simply-Fi Email: ").strip()
    password = args.password or getpass.getpass("Simply-Fi Password: ").strip()

    print("Authenticating against Simply-Fi CIAM...")
    tokens = cloud_authenticate(email, password, args.timeout)
    print("Fetching appliances...")
    appliances = cloud_list_appliances(tokens, args.timeout)

    print(f"\nFound {len(appliances)} appliance(s):")
    print(f"{'ID':<8} | {'MAC':<18} | {'Type':<14} | {'InterfaceType':<18} | {'Model'}")
    print("-" * 80)
    for entry in appliances:
        app = entry.get("appliance", entry)
        app_id = str(app.get("id", ""))
        mac = str(app.get("mac_address", ""))
        atype = str(app.get("appliance_type", ""))
        itype = str(app.get("interface_type", ""))
        model = str(app.get("appliance_model", ""))
        print(f"{app_id:<8} | {mac:<18} | {atype:<14} | {itype:<18} | {model}")


def handle_cloud_add(args: argparse.Namespace) -> None:
    """Handle 'cloud-add' CLI command."""
    email = args.email or input("Simply-Fi Email: ").strip()
    password = args.password or getpass.getpass("Simply-Fi Password: ").strip()

    tokens = cloud_authenticate(email, password, args.timeout)
    print(f"Registering appliance (Serial: {args.serial}, MAC: {args.mac})...")
    resp = cloud_add_appliance(
        tokens,
        args.serial,
        args.key,
        args.ssid,
        args.mac,
        args.security,
        args.purchase_date,
        args.timeout,
    )
    print("Appliance successfully registered on cloud account!")
    print(json.dumps(resp, indent=2))


def handle_cloud_remove(args: argparse.Namespace) -> None:
    """Handle 'cloud-remove' CLI command."""
    email = args.email or input("Simply-Fi Email: ").strip()
    password = args.password or getpass.getpass("Simply-Fi Password: ").strip()

    tokens = cloud_authenticate(email, password, args.timeout)
    print(f"Deleting appliance ID {args.id} from cloud account...")
    success = cloud_delete_appliance(tokens, args.id, args.timeout)
    if success:
        print(f"Appliance {args.id} removed successfully.")
    else:
        print(f"Failed to remove appliance {args.id}.")


def handle_provision_softap(args: argparse.Namespace) -> None:
    """Handle 'provision-softap' CLI command."""
    key = args.key or generate_random_key(16)
    print("=" * 60)
    print("Candy Simply-Fi SoftAP Wi-Fi Provisioning")
    print("=" * 60)
    print(f"SoftAP Gateway IP:   {args.softap_ip}:{args.port}")
    print(f"SoftAP SSID:         {args.softap_ssid}")
    print(f"Target Wi-Fi SSID:   {args.target_ssid}")
    print(f"Security Mode:       {args.security}")
    print(f"New Encryption Key:  {key}")
    print("=" * 60)

    print("Sending configuration to appliance...")
    resp = provision_softap(
        args.softap_ip,
        args.port,
        args.softap_ssid,
        args.bianca_axi,
        args.target_ssid,
        args.target_password,
        args.security,
        key,
        args.timeout,
    )
    print("\nSUCCESS! Appliance acknowledged Wi-Fi configuration.")
    print("Response payload:", resp)
    print("\nNext steps:")
    print("1. Reconnect your computer/phone to your home Wi-Fi network.")
    print(f"2. Add or update the appliance in Home Assistant using key: {key}")


def handle_wizard(args: argparse.Namespace) -> None:
    """Interactive wizard guiding the user through full de/re-provisioning."""
    print("=" * 70)
    print("  Candy Simply-Fi Appliance Lifecycle & Provisioning Wizard")
    print("=" * 70)
    print("This wizard will guide you through connecting your Candy/Hoover appliance")
    print("to your home Wi-Fi network without requiring the official mobile app.\n")

    print("Step 1: Put the appliance in Pairing Mode.")
    print("  - For Washers/Dryers: Turn the knob to the Wi-Fi icon or hold the")
    print("    Wi-Fi/Options button for 3-5 seconds until the Wi-Fi icon flashes.")
    print("  - For Dishwashers: Hold the Wi-Fi/Programme button until it beeps.\n")
    input("Press Enter once the appliance Wi-Fi icon is flashing...")

    print("\nStep 2: Choose Provisioning Method:")
    print("  [1] SoftAP Mode (Appliance broadcasts 'Candy_...' or 'WIFI_CONFIG_...' Wi-Fi)")
    print("  [2] BLE Mode (Bluetooth Low Energy - RapidÓ, Bianca, AXI models)")
    choice = input("Select [1 or 2]: ").strip()

    target_ssid = input("\nEnter your home 2.4 GHz Wi-Fi SSID: ").strip()
    target_pass = getpass.getpass("Enter your home Wi-Fi password: ").strip()
    key = generate_random_key(16)

    if choice == "1":
        softap_ssid = input("Enter the appliance SoftAP SSID (e.g. Candy_Lavatrice_...): ").strip()
        is_bianca = input("Is this a Bianca or AXI model? [y/N]: ").strip().lower() == "y"
        print(f"\nConnecting via SoftAP ({DEFAULT_SOFTAP_IP})...")
        print("Ensure this computer is currently connected to the appliance's Wi-Fi network!")
        input("Press Enter when connected to the appliance SoftAP...")

        try:
            provision_softap(
                DEFAULT_SOFTAP_IP,
                DEFAULT_SOFTAP_PORT,
                softap_ssid,
                is_bianca,
                target_ssid,
                target_pass,
                SECURITY_MODE_WPA_WPA2,
                key,
                args.timeout,
            )
            print("\nPROVISIONING SUCCESSFUL!")
            print(f"Appliance is connecting to '{target_ssid}' with XOR Key: {key}")
        except Exception as exc:
            print(f"\nProvisioning failed: {exc}", file=sys.stderr)
            return
    elif choice == "2":
        dev_addr = input("Enter BLE MAC Address or UUID: ").strip()
        import asyncio
        try:
            asyncio.run(
                provision_ble(
                    dev_addr,
                    target_ssid,
                    target_pass,
                    SECURITY_MODE_WPA_WPA2,
                    key,
                    args.timeout,
                )
            )
            print("\nBLE PROVISIONING SUCCESSFUL!")
            print(f"Appliance configured with XOR Key: {key}")
        except Exception as exc:
            print(f"\nBLE Provisioning failed: {exc}", file=sys.stderr)
            return
    else:
        print("Invalid choice, exiting.")
        return

    print("\nStep 3: Optional Cloud Registration")
    sync_cloud = input("Do you also want to register this appliance with your Simply-Fi cloud account? [y/N]: ").strip().lower() == "y"
    if sync_cloud:
        email = input("Simply-Fi Email: ").strip()
        passwd = getpass.getpass("Simply-Fi Password: ").strip()
        serial = input("Appliance 16-digit Serial Number: ").strip()
        mac = input("Appliance Wi-Fi MAC Address: ").strip()
        try:
            tokens = cloud_authenticate(email, passwd, args.timeout)
            cloud_add_appliance(
                tokens,
                serial,
                key,
                target_ssid,
                mac,
                SECURITY_MODE_WPA_WPA2,
                None,
                args.timeout,
            )
            print("Successfully registered on Simply-Fi cloud!")
        except Exception as exc:
            print(f"Cloud registration failed: {exc}", file=sys.stderr)

    print("\nWizard complete!")
    print(f"Home Assistant Setup Key: {key}")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Candy Simply-Fi Appliance Provisioning & Account Management Helper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP/Network timeout in seconds (default: 15.0)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # cloud-list
    p_clist = subparsers.add_parser("cloud-list", help="List appliances on Simply-Fi cloud account")
    p_clist.add_argument("--email", help="Account email")
    p_clist.add_argument("--password", help="Account password")
    p_clist.set_defaults(func=handle_cloud_list)

    # cloud-add
    p_cadd = subparsers.add_parser("cloud-add", help="Register an appliance on Simply-Fi cloud")
    p_cadd.add_argument("--email", help="Account email")
    p_cadd.add_argument("--password", help="Account password")
    p_cadd.add_argument("--serial", required=True, help="16-digit serial number")
    p_cadd.add_argument("--mac", required=True, help="Wi-Fi MAC address")
    p_cadd.add_argument("--key", required=True, help="16-character encryption key")
    p_cadd.add_argument("--ssid", required=True, help="Home Wi-Fi SSID")
    p_cadd.add_argument("--security", type=int, default=SECURITY_MODE_WPA_WPA2, help="Security mode (default: 3)")
    p_cadd.add_argument("--purchase-date", help="Purchase date YYYY-MM-DD")
    p_cadd.set_defaults(func=handle_cloud_add)

    # cloud-remove
    p_crem = subparsers.add_parser("cloud-remove", help="Remove an appliance from Simply-Fi cloud")
    p_crem.add_argument("--email", help="Account email")
    p_crem.add_argument("--password", help="Account password")
    p_crem.add_argument("--id", required=True, help="Appliance ID in cloud catalog")
    p_crem.set_defaults(func=handle_cloud_remove)

    # provision-softap
    p_softap = subparsers.add_parser("provision-softap", help="Push Wi-Fi credentials via SoftAP HTTP")
    p_softap.add_argument("--softap-ip", default=DEFAULT_SOFTAP_IP, help=f"SoftAP IP (default: {DEFAULT_SOFTAP_IP})")
    p_softap.add_argument("--port", type=int, default=DEFAULT_SOFTAP_PORT, help=f"SoftAP port (default: {DEFAULT_SOFTAP_PORT})")
    p_softap.add_argument("--softap-ssid", required=True, help="Appliance SoftAP SSID (e.g. Candy_Lavatrice_...)")
    p_softap.add_argument("--target-ssid", required=True, help="Target home Wi-Fi SSID")
    p_softap.add_argument("--target-password", required=True, help="Target home Wi-Fi password")
    p_softap.add_argument("--security", type=int, default=SECURITY_MODE_WPA_WPA2, help="Security mode (default: 3)")
    p_softap.add_argument("--key", help="16-character encryption key (auto-generated if omitted)")
    p_softap.add_argument("--bianca-axi", action="store_true", help="Set if appliance is Bianca or AXI model")
    p_softap.set_defaults(func=handle_provision_softap)

    # wizard
    p_wiz = subparsers.add_parser("wizard", help="Interactive step-by-step guided provisioning wizard")
    p_wiz.set_defaults(func=handle_wizard)

    return parser


def main() -> None:
    """Main CLI execution."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
