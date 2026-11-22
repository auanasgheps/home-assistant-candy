# Candy Simply-Fi & Hoover Wizard Appliance Manager (`appliance_manager.py`)

A standalone CLI and library utility to provision, re-provision, and manage the complete lifecycle of Candy Simply-Fi and Hoover Wizard connected appliances without relying on the official mobile app.

## WARNING: This tools is experimental and is largely untested. Do not rely on this tool if you don't have your Simpli-Fi app as backup.

---

## 1. Overview

While the integration manages appliance telemetry and control once connected to Home Assistant, `appliance_manager.py` manages the **network and cloud lifecycle**:
* **Wi-Fi Network Reconfiguration**: Reconnect an appliance to a new home Wi-Fi network (new router, changed SSID/password) after putting it into pairing mode.
* **100% Cloud-Free Setup**: Provision hardware Wi-Fi credentials with a locally generated encryption key, bypassing Simply-Fi cloud account creation entirely.
* **Cloud Account Management**: List, register, or delete appliances directly from your Simply-Fi / Hoover cloud catalog via CIAM PKCE authentication.
* **Multi-Transport Support**: Works over both legacy **SoftAP** (HTTP `192.168.0.1`) and modern **Bluetooth Low Energy (BLE)** (`wifible` on ESP32 models like RapidÓ, Bianca, and AXI).

---

## 2. Requirements & Installation

The tool is written in Python 3.10+ and uses the Python Standard Library for all cloud and SoftAP operations.

* **Standard Library**: Required for `cloud-*` and `provision-softap` commands (no `pip install` required).
* **Optional (`bleak`)**: Required only if using Bluetooth Low Energy provisioning (`provision-ble`):
  ```bash
  pip install bleak
  ```

---

## 3. Quickstart: Interactive Wizard

The easiest way to de/re-provision an appliance is to run the interactive step-by-step wizard:

```bash
python tools/appliance_manager.py wizard
```

The wizard will guide you through:
1. Putting the appliance into physical pairing mode.
2. Selecting between SoftAP Wi-Fi or BLE transport.
3. Entering your 2.4 GHz home Wi-Fi SSID and password.
4. Pushing the credentials to the machine.
5. (Optional) Syncing the new appliance and key to your Simply-Fi cloud account.

---

## 4. Command Reference

### 4.1 `provision-softap` (HTTP Gateway)
Pushes Wi-Fi credentials directly to the appliance's local configuration web server while connected to its temporary SoftAP network.

```bash
python tools/appliance_manager.py provision-softap \
  --softap-ssid "Candy_Lavatrice_445566" \
  --target-ssid "MyHomeNetwork" \
  [--target-password "MySecretPassword"] \
  [--softap-ip "192.168.0.1"] \
  [--port 80] \
  [--security 3] \
  [--key "16_CHAR_KEY_HERE"] \
  [--bianca-axi] \
  [--unencrypted]
```

#### Parameters:
* `--softap-ssid` *(Required)*: The exact SSID broadcasted by the machine (e.g. `Candy_Lavatrice_...` or `WIFI_CONFIG_...`). Used to calculate the temporary XOR encryption key.
* `--target-ssid` *(Required)*: Your home 2.4 GHz Wi-Fi SSID.
* `--target-password` *(Optional)*: Your home Wi-Fi password (prompted securely in-memory if omitted to avoid CLI history leakage).
* `--softap-ip` *(Optional, default: `192.168.0.1`)*: IP address of the appliance configuration gateway.
* `--port` *(Optional, default: `80`)*: Port of the configuration gateway.
* `--security` *(Optional, default: `3`)*: Wi-Fi security mode (`3` = WPA/WPA2, `2` = WEP, `0` = Open).
* `--key` *(Optional)*: 16-character alphanumeric key to program into the machine. If omitted, a cryptographically secure random key is generated automatically.
* `--bianca-axi` *(Optional flag)*: Must be passed if provisioning a Bianca or AXI model (these models use the first 8 characters of the SoftAP SSID instead of the last 8 for temporary key derivation).
* `--unencrypted` *(Optional flag)*: Sends configuration in plaintext without XOR encryption (for rare older models where `ENCRYPTED_CONFIGURATION = false`).

---

### 4.2 `provision-ble` (Bluetooth Low Energy)
Provisions appliances equipped with Espressif ESP32 modules (`"wifible"`: RapidÓ, Bianca, AXI) over Bluetooth Low Energy. Supports automatic device discovery if no address is supplied.

```bash
python tools/appliance_manager.py provision-ble \
  --target-ssid "MyHomeNetwork" \
  [--device-address "XX:XX:XX:XX:XX:XX"] \
  [--target-password "MySecretPassword"] \
  [--security 3] \
  [--key "16_CHAR_KEY_HERE"]
```

#### Parameters:
* `--target-ssid` *(Required)*: Your home 2.4 GHz Wi-Fi SSID.
* `--device-address` *(Optional)*: Bluetooth MAC address or CoreBluetooth UUID of the appliance. If omitted, the tool automatically scans for nearby Candy/Hoover appliances in pairing mode and prompts you to select one.
* `--target-password` *(Optional)*: Your home Wi-Fi password (prompted securely if omitted).
* `--security` *(Optional, default: `3`)*: Security mode (`3` = WPA/WPA2).
* `--key` *(Optional)*: 16-character alphanumeric key. If omitted, a random key is generated.

---

### 4.3 `cloud-list`
Queries your Simply-Fi cloud account via CIAM PKCE authentication and lists all registered appliances with their IDs, MAC addresses, types, local encryption keys, and model codes.

```bash
python tools/appliance_manager.py cloud-list \
  [--email "user@example.com"] \
  [--password "account_password"]
```
*(If credentials are not passed on the CLI, the tool prompts for them interactively in-memory).*

---

### 4.4 `cloud-add`
Manually registers or re-links an appliance in your Simply-Fi cloud account so official apps stay synchronized with your local encryption key. All inputs are strictly validated (serial must be 16 digits, key must be 16 alphanumeric characters, MAC must be 12 hex digits).

```bash
python tools/appliance_manager.py cloud-add \
  --serial "3100876543210987" \
  --mac "AA:BB:CC:DD:EE:FF" \
  --key "16_CHAR_KEY_HERE" \
  --ssid "MyHomeNetwork" \
  [--security 3] \
  [--purchase-date "YYYY-MM-DD"]
```

---

### 4.5 `cloud-remove`
Deletes and unlinks an appliance from your Simply-Fi cloud account by its cloud database ID. Prompts for confirmation by default before performing permanent cloud removal.

```bash
python tools/appliance_manager.py cloud-remove \
  --id "123456" \
  [--yes]
```

---

## 5. Walkthroughs & Use Cases

### Use Case 1: Changing Wi-Fi Network on an Appliance
If you changed routers or Wi-Fi passwords and your appliance lost connection:

1. **Activate Pairing Mode**: Put your machine into pairing mode:
   * *Washers & Dryers*: Turn the knob to the **Wi-Fi** icon (or hold the Wi-Fi button until the icon flashes).
   * *Dishwashers*: Hold down the Wi-Fi/Programme button for 3–5 seconds until it beeps.
2. **Connect to SoftAP**: On your computer/laptop, join the machine's temporary Wi-Fi network (e.g. `Candy_Lavatrice_445566`).
3. **Run Provisioning**:
   ```bash
   python tools/appliance_manager.py provision-softap \
     --softap-ssid "Candy_Lavatrice_445566" \
     --target-ssid "NewHomeWiFi" \
     --target-password "NewPassword123"
   ```
4. **Reconnect**: Reconnect your computer to your home Wi-Fi.
5. **Home Assistant**: Check your router for the appliance's new IP address. If the IP address changed, update your integration entry (or assign a DHCP reservation to keep the previous IP).

---

### Use Case 2: 100% Cloud-Free / Local-Only Onboarding
If you want to use the appliance with Home Assistant without creating a Simply-Fi account:

1. Put the machine into pairing mode.
2. Connect to the appliance SoftAP.
3. Run `provision-softap`:
   ```bash
   python tools/appliance_manager.py provision-softap \
     --softap-ssid "Candy_Lavatrice_445566" \
     --target-ssid "HomeWiFi" \
     --target-password "SecretPassword"
   ```
4. Note the output:
   ```
   New Encryption Key:  k8F29aL01pxM39Qz
   ```
5. In Home Assistant, navigate to **Settings $\rightarrow$ Devices & Services $\rightarrow$ Add Integration $\rightarrow$ Candy**:
   * Enter the appliance IP address.
   * Paste `k8F29aL01pxM39Qz` into the encryption key field.
   * You now have complete local control with zero cloud account dependency.

---

## 6. Technical & Protocol Grounding

This tool is strictly grounded in decompiled Android APK bytecode (`classes*.dex`):

| Layer | Implementation Details | Authoritative APK Source |
| :--- | :--- | :--- |
| **SoftAP Wire Endpoint** | `GET http://192.168.0.1/http-config.json?encrypted=1&data=<hex>` | `ConnectionManager.java:1030` |
| **SoftAP Key Derivation** | Standard: last 8 chars repeated (`cleanSSID(ssid).substring(len-8) * 2`)<br>Bianca/AXI: first 8 chars repeated (`cleanSSID(ssid).substring(0,8) * 2`) | `CandySecurityUtility.java:105` |
| **Encrypted Response** | The appliance encrypts its HTTP 200 response with the **new** provisioned `ENCRYPT_KEY` | `ConnectionManager.java:1186` |
| **BLE GATT Service** | UUID `0000a002-0000-1000-8000-00805f9b34fb`<br>Config Char `0xC302`, MAC Char `0xC300` | `CandyEnrollmentService` |
| **BLE Packet Framing** | `[0xA5] [Length] [0x16] [NTW_MODE=...&SSID=...&PASSWORD=...&ENCRYPT_KEY=...] [CRC16]` | `EnrollApplianceBLECommand.java` |
| **CRC-16 Algorithm** | ISO 13239 with polynomial `0x6363` (25443), inverted bitwise (`~crc & 0xFFFF`) | `NFCUtility.java:64` |
| **Cloud Registration** | `POST https://simply-fi.herokuapp.com/api/v1/appliances.json` | `ConnectionManager.java:971` |
| **Cloud Deletion** | `DELETE https://simply-fi.herokuapp.com/api/v1/appliances/{id}` | `APIAccessor.java:506` |
| **CIAM Authentication** | OAuth2 PKCE via `https://api-iot.he.services/ciam/{authorize,token}` | `query_cloud.py` |
