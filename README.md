# Candy Home Assistant Component

[![Run tests](https://github.com/bigmoby/home-assistant-candy/actions/workflows/lint.yml/badge.svg)](https://github.com/bigmoby/home-assistant-candy/actions/workflows/lint.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Donate](https://img.shields.io/badge/donate-BuyMeCoffee-yellow.svg)](https://www.buymeacoffee.com/bigmoby)

A highly optimized custom component for [Home Assistant](https://homeassistant.io) that effortlessly integrates Candy, Haier, and Simply-Fi connected home appliances.

Fully compliant with strictly-typed Home Assistant (>= 2024.x) development standards, it features **Zero-Configuration Automatic Decryption**—making setup purely plug-and-play.

---

## ✨ Features

- **Supported appliances**:
  - 🧺 Washing Machine
  - 🌫️ Tumble Dryer
  - 🔪 Dishwasher
  - 🍳 Oven
- **Zero-Config Decryption:** Say goodbye to manually extracting encryption keys. This integration boasts a natively built-in *sliding-window/known-plaintext* algorithm that unlocks your device seamlessly in fractions of a second during setup.
- **Strict HA Compatibility:** Follows the rigorous MyPy styling standards enforced by Home Assistant 2025.
- Uses the local device API for real-time responsiveness.
- Creates dedicated, native semantic sensors (e.g., remaining time, current status, machine cycle) and exposes granular information cleanly as sensor attributes.

---

## 🛠️ Installation

### Method 1: HACS (Recommended)
1. Install [HACS](https://hacs.xyz/).
2. Go to the HACS integrations page, search for `Candy Simply-Fi` and download it.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services**, click **Add integration** and search for `Candy`.
5. Enter the **IP Address** of your appliance.
6. The integration will automatically authenticate, decrypt if necessary, and assign the appliance to your dashboard!

### Method 2: Manual
1. Copy the `custom_components/candy` folder into your Home Assistant's `custom_components` directory.
2. Restart Home Assistant and add `Candy` via the UI.

---

## 🚀 Built-in Debugging Tool

Are you a developer, or do you want to inspect what raw JSON your specific appliance is throwing over your network? We've got you covered:

Inside the `tools/` folder of this repository, you'll find the standalone `simplyfi.py` script. You can run it effortlessly from any terminal independent from Home Assistant!

```bash
python3 tools/simplyfi.py <YOUR_APPLIANCE_IP_ADDRESS>
```

This is incredibly useful for validating your appliance network reachability or diagnosing new payloads.

---

## 🔍 Finding Your Appliance on the Network

Not sure what IP address your Candy appliance has? Run this one-liner from any terminal on the **same local network** as your device.

> **Prerequisite:** replace `192.168.1` with your actual subnet if different (check your router settings).

```bash
# Scan the entire subnet for Candy Simply-Fi appliances
for i in $(seq 1 254); do
  result=$(curl -s --max-time 1 "http://192.168.1.$i/http-read.json?encrypted=0" 2>/dev/null)
  [ -n "$result" ] && echo "192.168.1.$i: $result"
done
```

The script probes every host on the subnet for the Candy local API endpoint. Any appliance that responds will print its IP address alongside its raw JSON status — for example:

```
192.168.1.79: { "statusLavatrice": { "WiFiStatus": "1", ... } }
```

Use that IP when configuring the integration in Home Assistant.

---

## 🙋 My device isn't supported. Can you help?

Absolutely! If you have an appliance that is not supported yet (or you notice odd readings), head over to the [Discussions section](https://github.com/bigmoby/home-assistant-candy/discussions/categories/device-support-improvements). Open a new thread or comment to an existing one with the following information:

1. The raw status API response of your device (Please use the provided `tools/simplyfi.py` inside this repo to query your IP and get the full JSON).
2. A brief, intuitive explanation of what you think each field correlates to based on the machine's state (e.g., _The `SpinSp` field reads "8", meaning Spin speed 800 RPM in my model_).

---

## 👨‍💻 Develop

If you want to contribute, test features or build new integrations, the environment is fully automated.

### Quick Start
Setup the development environment using our rapid bash scripts:
```bash
make setup
```

### Available Commands
Use the `Makefile` for all standard operations:
```bash
make setup         # Setup development environment and venv
make check         # Run all checks (lint + test)
make lint          # Run ruff spacing and mypy static type checking
make format        # Format python code to meet standard
make test          # Run tests with coverage
make clean         # Deep clean cache folders
```

### Development Tools (Pre-Commit)
We rely on Github rigorous standards to maintain 100% Home Assistant compliance.
You can install our native pre-commit hooks that format and protect every single push:
```bash
make pre-commit-install
```

---

## Sponsor

Please, if You want support this kind of projects:

<a href="https://www.buymeacoffee.com/bigmoby" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

Many Thanks,

Fabio Mauro
