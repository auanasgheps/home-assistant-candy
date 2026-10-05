# Remote Control Guide — Washing Machines & Washer-Dryers

This guide explains how to use Full Control mode in Home Assistant to monitor, configure, and operate Candy and Hoover washing machines and washer-dryer combos.

---

## Table of Contents

- [Quick Start: Enabling Remote Control](#quick-start-enabling-remote-control)
- [Remote Control Status & Safety Gating](#remote-control-status--safety-gating)
- [Cycle Controls (Start, Pause, Resume, Stop)](#cycle-controls-start-pause-resume-stop)
- [Configuring Programs & Options](#configuring-programs--options)
  - [Standard Washing Machines](#standard-washing-machines)
  - [Washer-Dryer Combos](#washer-dryer-combos)
- [Maintenance Counters & Diagnostics](#maintenance-counters--diagnostics)
- [Smart Fault & Error Notifications](#smart-fault--error-notifications)
- [Ready-Made Dashboards](#ready-made-dashboards)
- [Behind the Scenes: Polling & Response Times](#behind-the-scenes-polling--response-times)

---

## Quick Start: Enabling Remote Control

To control your appliance from Home Assistant, remote operation must be enabled on the physical machine:

1. Turn the appliance on.
2. Turn the physical program dial/knob to the dedicated **Wi-Fi** or **Remote** position (depending on your model, labeled as `Wi-Fi`, `Remote Control`, or `One Touch / Wi-Fi`).
3. Ensure the door is securely closed.

When enabled, the integration reports Remote Control as active:
- `binary_sensor.<device>_remote_control` turns **On**.
- The `remote_control` attribute on your main status sensor (`sensor.<device>`) reports `true`.
- All control buttons, program selectors, and option switches in Home Assistant become active and ready for use.

---

## Remote Control Status & Safety Gating

Candy and Hoover appliances enforce local safety: **the physical dial always takes precedence over the network**.

If someone turns the machine's dial to a physical wash cycle (e.g., *Cottons 60°*), the appliance switches to local mode. It continues streaming live sensor data and progress to Home Assistant, but safely ignores incoming network commands.

### Which entities are gated?

When Remote Control is off (or when the appliance is powered off), Home Assistant marks all command entities as `unavailable` to prevent sending commands that the machine would reject:

- **Cycle buttons:** Start, Pause, Resume, and Stop
- **Program & parameter selectors:** Program, Program Type, Dry Setting, Temperature, Spin Speed, Soil Level
- **Option switches:** Prewash, Hygiene, Steam, Anti-Crease, Night Cycle, Extra Rinse, AquaPlus, Downloaded Programs
- **Delay timer:** Delay start duration slider
- **Diagnostic buttons:** Full Check-up and Limescale Cleaning buttons

> [!NOTE]
> **Maintenance reset buttons** remain available even when Remote Control is off or the appliance is powered off. These buttons update your maintenance counter baselines locally within Home Assistant without sending commands to the appliance.

---

## Cycle Controls (Start, Pause, Resume, Stop)

The integration provides complete cycle management:

| Button | Entity | Description |
|---|---|---|
| **Start** | `button.<device>_start_wash` | Starts the cycle with your currently selected program, temperature, spin speed, soil level, delay, and options. |
| **Pause** | `button.<device>_pause_wash` | Pauses an active wash or dry cycle. |
| **Resume** | `button.<device>_resume_wash` | Resumes a paused cycle (paused via Home Assistant, the front panel button, or opening the door) without losing remaining time or resetting settings. |
| **Stop** | `button.<device>_stop_wash` | Cancels the active cycle and drains/unlocks the machine according to its built-in safety sequence. |

> [!TIP]
> **Pause & Resume Compatibility:** Most modern Candy and Hoover appliances support remote Pause and Resume. However, select hardware series (such as Candy Bianca or DualTech appliances) do not support remote pause at the firmware level. On these models, Pause and Resume buttons are automatically hidden.

---

## Configuring Programs & Options

The interface automatically tailors its options depending on whether your appliance is a standard washing machine or a washer-dryer combo.

| Feature | Standard Washing Machine | Washer-Dryer Combo |
|---|---|---|
| **Program Type Selector** | Not needed | `select.<device>_program_type` (Washing, Wash & Dry, Drying) |
| **Dry Setting Selector** | Not needed | `select.<device>_dry_setting` (Dryness presets & timed dry) |
| **Active Dry Target Sensor** | Not needed | `sensor.<device>_dry_target` (Live dry stage & cooldown) |
| **Program List** | All wash & special cycles | Dynamically filtered based on selected Program Type |
| **Estimated Duration** | Wash cycle + soil + steam time | Combined wash and dry estimation |
| **Scheduled End Time** | Current time + delay + wash time | Current time + delay + combined wash & dry time |

### Standard Washing Machines

Starting a cycle is a simple 4-step process:

1. **Select a program:** Choose from `select.<device>_wash_program` (or toggle a downloadable/special program).
2. **Adjust parameters:** Customize temperature (`select.<device>_wash_temperature`), spin speed (`select.<device>_wash_spin_speed`), and soil level (`select.<device>_wash_soil_level`).
3. **Set options & delay (optional):** Toggle option switches (e.g. Steam, Prewash, Extra Rinse) or set a delay duration slider.
4. **Press Start:** Tap `button.<device>_start_wash`.

### Washer-Dryer Combos

Washer-dryer combos offer dedicated controls to seamlessly handle washing, combined wash & dry, and standalone drying cycles:

#### 1. Choose the Program Type (`select.<device>_program_type`)
- **Washing:** Standard wash cycle only. The dry setting is locked to *No dry*.
- **Wash & Dry:** Automatic continuous cycle that washes and immediately transitions into drying. The program selector automatically filters to show only programs compatible with continuous drying, and sets the default dry setting to *Cupboard dry*.
- **Drying:** Standalone dry cycle without water washing. Only dedicated drying cycles (e.g. High Heat, Low Heat, Wool Dry) appear in the program dropdown.

#### 2. Select the Dry Setting (`select.<device>_dry_setting`)
Choose your target drying level or timed duration:
- **Dryness Presets:** `Cupboard dry` (standard default), `Iron dry`, or `Extra dry`.
- **Timed Drying:** `30 minutes`, `60 minutes`, `90 minutes`, or `120 minutes`.
- **`No dry`:** Used when operating in standard wash-only mode.

#### 3. Automatic Safeguards
- **Incompatible Program Protection:** Selecting a wash cycle that cannot be machine-dried (such as Delicates or Rapid cycles) automatically reverts the dry setting to *No dry*.
- **Automatic Parameter Zeroing:** When starting a standalone drying program, the integration automatically zeroes out wash temperature, spin speed, and soil levels so the machine accepts the drying instruction without errors.
- **Running Lockout:** Dry settings cannot be modified while a cycle is actively running.
- **Cool-down Monitoring:** The `sensor.<device>_dry_target` sensor reports the active drying target and tracks the drum cooldown phase at the end of drying.

---

## Maintenance Counters & Diagnostics

The integration tracks cycle counts and alerts you when periodic maintenance is needed, mirroring the official app's reminders:

| Routine | Threshold | Recommended Action | Reset Behavior |
|---|---|---|---|
| **Full Check-up** | Every 100 cycles | Run diagnostic via `button.<device>_full_checkup` | **Automatic:** Resets when test completes (manual reset button fallback available) |
| **Limescale Cleaning** | Every 85–110 cycles (based on water hardness) | Run autoclean via `button.<device>_limescale_cleaning` | **Automatic:** Resets when autoclean completes (manual reset button fallback available) |
| **Filter Cleaning** | Every 100 cycles | Physically inspect and clean the debris filter | **Manual:** Press `button.<device>_reset_filter_counter` after cleaning |

### How Maintenance Lifecycle Works
- **Due Alerts:** When a counter reaches 0 remaining cycles, Home Assistant posts a persistent notification in your language. The counter stays at 0 (and keeps you reminded) until reset.
- **Cycle Preparation Guidance:** When you start a Full Check-up or Limescale Cleaning cycle from Home Assistant, a notification appears with official preparation instructions (e.g. ensuring drum is empty, adding descaler).
- **Automatic Completion & Dismissal:** Once a Check-up or Limescale Cleaning cycle finishes successfully, Home Assistant automatically updates the counter baseline, clears the alert, and notifies you of successful completion.

---

## Smart Fault & Error Notifications

When the appliance reports a problem (such as an error code):

- **Vendor Troubleshooting Steps:** Home Assistant displays a persistent notification with official, step-by-step guidance translated into your configured language (e.g., checking water pressure, clearing the inlet filter, balancing the load, or unblocking the pump).
- **Real-Time Updates:** If the machine's reported error code changes, the notification automatically updates with the new diagnosis.
- **Auto-Dismissal:** As soon as you resolve the issue on the appliance and the machine clears the fault, the notification automatically dismisses itself.
- **Washer-Dryer Diagnostics:** Specific faults (such as drying airflow issues) include tailored advice to check ventilation or cool-down.

---

## Ready-Made Dashboards

Pre-configured Lovelace dashboard cards are available in the [`dashboard/`](../dashboard/) directory (requires the [Mushroom](https://github.com/piitaya/lovelace-mushroom) card):

- **[Standard Washing Machine Card](../dashboard/washing-machine.yaml):** Full control panel with program selection, spin/temp adjustments, start/pause/stop buttons, detergent dosing chips, and finish time estimates.
- **[Washer-Dryer Card](../dashboard/washer-dryer.yaml):** All washing controls plus program type switching (wash/dry/both), dry setting selectors, live dry target chips, and animated drying state icons.
- **[Maintenance & Diagnostics Card](../dashboard/maintenance.yaml):** Live counter progress bars, one-click diagnostic test buttons, and counter reset controls.

---

## Behind the Scenes: Polling & Response Times

The integration is optimized to balance fast dashboard feedback with minimal network traffic:

- **Instant Command Settling (~5 seconds):** When you tap a button (such as Start or Pause), Home Assistant temporarily disables the controls for 5 seconds. This brief window gives the appliance firmware time to acknowledge the command and update its internal state before Home Assistant requests a fresh status update.
- **Active Polling (60 seconds):** While the appliance is turned on and connected, Home Assistant refreshes telemetry every 60 seconds.
- **Fast Wake-up Detection (20 seconds):** When the machine is turned off or in standby, the integration checks every 20 seconds. This allows Home Assistant to detect when you turn on the appliance at the dial almost immediately without overloading your local network.
