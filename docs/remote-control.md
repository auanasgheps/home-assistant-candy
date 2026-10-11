# Remote Control Guide — Washing Machines, Washer-Dryers & Tumble Dryers

This guide explains how to use Full Control mode in Home Assistant to monitor, configure, and operate Candy and Hoover washing machines, washer-dryer combos, and standalone tumble dryers.

---

## Table of Contents

- [Quick Start: Enabling Remote Control](#quick-start-enabling-remote-control)
- [Remote Control Status & Safety Gating](#remote-control-status--safety-gating)
- [Cycle Controls (Start, Pause, Resume, Stop, Anti-Crease)](#cycle-controls-start-pause-resume-stop-anti-crease)
- [Configuring Programs & Options](#configuring-programs--options)
  - [Standard Washing Machines](#standard-washing-machines)
  - [Washer-Dryer Combos](#washer-dryer-combos)
  - [Standalone Tumble Dryers](#standalone-tumble-dryers)
- [Maintenance, Hardware Alerts & Diagnostics](#maintenance-hardware-alerts--diagnostics)
  - [Washing Machines & Washer-Dryers (Cycle Counters)](#washing-machines--washer-dryers-cycle-counters)
  - [Standalone Tumble Dryers (Hardware Sensor Alerts & Resets)](#standalone-tumble-dryers-hardware-sensor-alerts--resets)
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

- **Cycle buttons:** Start (`start_wash` / `start_drying`), Pause (`pause_wash` / `pause_drying`), Resume (`resume_wash` / `resume_drying`), Stop (`stop_wash` / `stop_drying`), and Cancel Anti-Crease (`cancel_anti_crease` on dryers)
- **Program & parameter selectors:** Program (`wash_program` / `dryer_program`), Program Type (`program_type`), Dry Setting (`dry_setting`), Dry Level (`dry_level`), Timed Drying (`timed_drying`), Temperature, Spin Speed, Soil Level
- **Option switches (washers):** Prewash, Hygiene, Steam, Anti-Crease, Night Cycle, Extra Rinse, AquaPlus, Downloaded Programs
- **Delay timer:** Delay start duration input (`number.<device>_delay`)
- **Diagnostic buttons:** Full Check-up and Limescale Cleaning (washing machines); Self Check-up and Reset Warnings (tumble dryers)

> [!NOTE]
> **Maintenance reset buttons vs. Hardware warning resets:**
> - **Washing Machines & Combos:** Maintenance reset buttons (`button.<device>_reset_*`) update software counter baselines locally within Home Assistant without transmitting network commands to the appliance. They remain available even when Remote Control is off or the appliance is powered down.
> - **Standalone Tumble Dryers:** The Reset Warnings button (`button.<device>_reset_warnings`) dispatches a live hardware reset instruction to the machine's microcontroller to unlatch warning registers. It requires Remote Control to be enabled.

---

## Cycle Controls (Start, Pause, Resume, Stop, Anti-Crease)

The integration provides complete cycle management for all supported appliance types:

### Washing Machines & Washer-Dryer Combos

| Button | Entity | Description |
|---|---|---|
| **Start** | `button.<device>_start_wash` | Starts the cycle with your currently selected program, temperature, spin speed, soil level, delay, and options. |
| **Pause** | `button.<device>_pause_wash` | Pauses an active wash or dry cycle. |
| **Resume** | `button.<device>_resume_wash` | Resumes a paused cycle (paused via Home Assistant, the front panel button, or opening the door) without losing remaining time or resetting settings. |
| **Stop** | `button.<device>_stop_wash` | Cancels the active cycle and drains/unlocks the machine according to its built-in safety sequence. |

> [!TIP]
> **Pause & Resume Compatibility (Washing Machines):** Most modern Candy and Hoover appliances support remote Pause and Resume. However, select hardware series (such as Candy Bianca or DualTech washing machines) do not support remote pause at the firmware level. On these models, Pause and Resume buttons are automatically hidden.

### Standalone Tumble Dryers

| Button | Entity | Description |
|---|---|---|
| **Start** | `button.<device>_start_drying` | Starts drying with your currently selected program, target dry level, timed drying duration, and delay. |
| **Pause** | `button.<device>_pause_drying` | Pauses an active drying cycle without resetting program progress. |
| **Resume** | `button.<device>_resume_drying` | Resumes a paused drying cycle from where it left off. |
| **Stop** | `button.<device>_stop_drying` | Cancels the active drying cycle immediately. |
| **Cancel Anti-Crease** | `button.<device>_cancel_anti_crease` | Immediately cancels the gentle drum tumbling (anti-crease) phase that runs after drying completes. |

---

## Configuring Programs & Options

The interface automatically tailors its options depending on whether your appliance is a standard washing machine, a washer-dryer combo, or a standalone tumble dryer.

| Feature | Standard Washing Machine | Washer-Dryer Combo | Standalone Tumble Dryer |
|---|---|---|---|
| **Program Selector** | `select.<device>_wash_program` | `select.<device>_wash_program` | `select.<device>_dryer_program` |
| **Program Type Selector** | Not needed | `select.<device>_program_type` (Washing, Wash & Dry, Drying) | Not needed (all cycles dry) |
| **Dry Level Selector** | Not needed | Handled by `select.<device>_dry_setting` | `select.<device>_dry_level` (Iron dry, Hang dry, Store dry, Bone dry) |
| **Timed Drying Selector** | Not needed | Integrated into `select.<device>_dry_setting` | `select.<device>_timed_drying` (30, 45, 60, 90, 120 min) |
| **Active Target / Status Sensor** | `sensor.<device>_wash_cycle_status` | `sensor.<device>_dry_target` (Stage & cooldown) | `sensor.<device>_dry_level` & `sensor.<device>_dryer_cycle_status` |
| **Program List** | All wash & special cycles | Dynamically filtered based on selected Program Type | Localized tumble dryer cycles |
| **Cycle Adjustments** | Temp, spin speed, soil level, wash options | Temp, spin speed, soil level, wash options (during wash) | Target dry level or timed duration override |
| **Estimated Duration** | Wash cycle + soil + steam time | Combined wash and dry estimation | Sensor remaining time (`sensor.<device>_dryer_cycle_remaining_time`) |
| **Delay Timer** | `number.<device>_delay` (30 min increments) | `number.<device>_delay` (30 min increments) | `number.<device>_delay` (60 min increments, up to 24 h) |

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

### Standalone Tumble Dryers

Operating a standalone tumble dryer is straightforward with automatic sensor-based dryness or fixed timed drying:

#### 1. Choose a Program (`select.<device>_dryer_program`)
Select your cycle from `select.<device>_dryer_program` (such as *Eco Cotton*, *Whites*, *Synthetics*, *Wool*, *Allergies*, *Anti-Odours*, etc.). Cycle names are automatically localized based on your configured appliance language.

#### 2. Configure Dryness or Timed Duration
Choose between automatic sensor drying or a fixed manual duration:
- **Automatic Dryness Level (`select.<device>_dry_level`):** The dryer automatically stops when humidity sensors detect the target moisture level:
  - `Iron dry`: Leaves slight moisture in fabrics for effortless ironing.
  - `Hang dry`: Leaves garments ready to place directly onto hangers.
  - `Store dry`: Standard everyday dryness for folding and wardrobe storage.
  - `Bone dry`: Extra intensive drying for thick towels, bathrobes, and heavy fabrics.
- **Timed Drying Override (`select.<device>_timed_drying`):** If you prefer to dry for a preset time regardless of humidity sensors, choose `30 minutes`, `45 minutes`, `60 minutes`, `90 minutes`, or `120 minutes`. Set to `Off` to return to sensor-based drying.

#### 3. Set a Delayed Start (Optional)
Use `number.<device>_delay` to schedule drying to start at a later time (configurable in 1-hour increments up to 24 hours / 1440 minutes).

#### 4. Press Start (`button.<device>_start_drying`)
Tap Start to initiate the cycle.

#### 5. Automatic Safeguards & Post-Cycle Behavior
- **Door Open Protection:** The appliance checks `binary_sensor.<device>_door` and prevents starting if the door is open.
- **Cool-Down Phase:** Toward the end of the cycle, heating shuts off while the drum continues tumbling to aerate and cool down garments. The status sensor (`sensor.<device>_dryer_cycle_status`) explicitly reports *Cooling down*.
- **Anti-Crease Tumbling:** After the cycle completes, the dryer enters a gentle anti-crease tumbling phase to keep clothes wrinkle-free until you empty the drum. To end anti-crease tumbling immediately, press `button.<device>_cancel_anti_crease`.

---

## Maintenance, Hardware Alerts & Diagnostics

Maintenance workflows differ between appliance types: washing machines and washer-dryers track usage using cumulative cycle counters, whereas standalone tumble dryers rely directly on real-time hardware sensors and float switches.

### Washing Machines & Washer-Dryers (Software Cycle Counters)

For washing machines and washer-dryer combos, the integration tracks wash cycle counts and alerts you when periodic maintenance is needed, mirroring the official app's reminders:

| Routine | Threshold | Recommended Action | Reset Behavior |
|---|---|---|---|
| **Full Check-up** | Every 100 cycles | Run diagnostic via `button.<device>_full_checkup` | **Automatic:** Resets when test completes (manual reset button fallback available) |
| **Limescale Cleaning** | Every 85–110 cycles (based on water hardness) | Run autoclean via `button.<device>_limescale_cleaning` | **Automatic:** Resets when autoclean completes (manual reset button fallback available) |
| **Filter Cleaning** | Every 100 cycles | Physically inspect and clean the debris filter | **Manual:** Press `button.<device>_reset_filter_counter` after cleaning |

#### How Software Maintenance Lifecycle Works
- **Due Alerts:** When a counter reaches 0 remaining cycles, Home Assistant posts a persistent notification in your language. The counter stays at 0 (and keeps you reminded) until reset.
- **Cycle Preparation Guidance:** When you start a Full Check-up or Limescale Cleaning cycle from Home Assistant, a notification appears with official preparation instructions (e.g. ensuring drum is empty, adding descaler).
- **Automatic Completion & Dismissal:** Once a Check-up or Limescale Cleaning cycle finishes successfully, Home Assistant automatically updates the counter baseline, clears the alert, and notifies you of successful completion.

### Standalone Tumble Dryers (Hardware Sensor Alerts & Resets)

Standalone tumble dryers do not require manual cycle counting or descaling baselines. Instead, their microcontrollers monitor live physical switches and pressure sensors:

| Hardware Component | Entity | Hardware Trigger | Required Action |
|---|---|---|---|
| **Condensate Water Tank** | `binary_sensor.<device>_water_tank_full` | Reservoir float switch detects tank is full ($\ge 10\text{ s}$) | Empty the water collection drawer |
| **Lint / Fluff Filter** | `binary_sensor.<device>_clean_filter` | Airflow resistance and thermal sensors detect lint blockage | Clean lint filter mesh |
| **Reset Warnings** | `button.<device>_reset_warnings` | Machine latches warning indicators | Clears persistent warning flags on appliance hardware |
| **Self Check-up** | `button.<device>_check_up` | User triggers diagnostic test | Runs internal component test; state shown on `sensor.<device>_check_up_state` |

#### How Dryer Hardware Alerts Work
- **Live Warning Banners & Notifications:** When the water tank is full or the lint filter requires cleaning, the corresponding binary sensor turns **On** and Home Assistant issues a persistent notification with clear instructions.
- **Fault Escalation Prevention:** If ignored, a full water tank automatically pauses the machine and escalates to hardware error `E03`, while an occluded lint filter escalates to airflow error `E07`.
- **Clearing Hardware Warnings:** After emptying the tank or cleaning the filter mesh, press `button.<device>_reset_warnings` while Remote Control is active to clear the machine's warning latches.
- **Electronic Self Check-up:** Tap `button.<device>_check_up` to run the dryer's factory self-diagnostic test. The diagnostic progress is tracked via `sensor.<device>_check_up_state` (`0` = Idle, `1` = Running, `2` = Complete/Passed). When the test completes, Home Assistant automatically acknowledges and resets the diagnostic state on the appliance.

---

## Smart Fault & Error Notifications

When any appliance reports an operational fault or hardware issue:

- **Vendor Troubleshooting Steps:** Rather than displaying obscure codes, Home Assistant presents a persistent notification with official, step-by-step guidance translated into your configured appliance language (e.g., checking water pressure, clearing the inlet filter, balancing the load, or unblocking the pump).
- **Real-Time Updates:** If the machine's reported error code changes, the notification automatically updates with the new diagnosis.
- **Auto-Dismissal:** As soon as you resolve the issue on the appliance and the machine clears the fault, the notification automatically dismisses itself.
- **Washing Machine & Combo Diagnostics:** Monitors water inlet, drainage, drum motor, and heating faults (such as `E02`, `E03`, `E12`, and `E16`).
- **Tumble Dryer Diagnostics:** Tracks 14 dedicated dryer fault codes on `sensor.<device>_dryer_error` (such as `E03` water container full, `E05`/`E14` temperature probes, `E07` filter/airflow occlusion, `E11` condenser overheating, and `E13` compressor circuit).

### Automation Triggers

You can trigger automations directly using native Home Assistant device automation triggers:
- **Washing Machines & Washer-Dryers:** Washing started, washing completed, check-up reminder, descaling reminder, filter cleaning reminder, error reported.
- **Standalone Tumble Dryers:** Drying started, drying completed, filter cleaning reminder, water tank full reminder, error reported.

---

## Ready-Made Dashboards

Pre-configured Lovelace dashboard cards are available in the [`dashboard/`](../dashboard/) directory (requires the [Mushroom](https://github.com/piitaya/lovelace-mushroom) card):

### Operational Cards (Select the card matching your appliance)
- **[Standard Washing Machine Card](../dashboard/washing-machine.yaml):** Operational control panel for standard washing machines (program selection, spin/temp adjustments, start/pause/stop buttons, detergent dosing chips, and finish time estimates). *Pair with `maintenance.yaml` for maintenance counters.*
- **[Washer-Dryer Card](../dashboard/washer-dryer.yaml):** Operational control panel for washer-dryer combos (all washing controls plus program type switching between wash/dry/both, dry setting selectors, live dry target chips, and animated drying state icons). *Pair with `maintenance.yaml` for maintenance counters.*
- **[Tumble Dryer Card](../dashboard/tumble-dryer.yaml):** Complete all-in-one control panel for standalone tumble dryers (program selection, dryness level and timed drying selectors, live lint filter and condensate water tank warning alerts, anti-crease tumbling cancellation, electronic check-up, and hardware warning resets). *A separate maintenance card is not needed for dryers.*

### Maintenance & Diagnostics Card (Washing Machines & Washer-Dryers)
- **[Maintenance & Diagnostics Card](../dashboard/maintenance.yaml):** Dedicated maintenance card for **Washing Machines and Washer-Dryer combos**. Displays live counter progress bars (Limescale Cleaning, Full Check-up, Debris Filter), one-click autoclean triggers, and baseline reset buttons. *(Not used for standalone tumble dryers, which have their hardware alerts and diagnostics built directly into `tumble-dryer.yaml`).*

---

## Behind the Scenes: Polling & Response Times

The integration is optimized to balance fast dashboard feedback with minimal network traffic:

- **Instant Command Settling (~5 seconds):** When you tap a button (such as Start or Pause), Home Assistant temporarily disables the controls for 5 seconds. This brief window gives the appliance firmware time to acknowledge the command and update its internal state before Home Assistant requests a fresh status update.
- **Active Polling (60 seconds):** While the appliance is turned on and connected, Home Assistant refreshes telemetry every 60 seconds.
- **Fast Wake-up Detection (20 seconds):** When the machine is turned off or in standby, the integration checks every 20 seconds. This allows Home Assistant to detect when you turn on the appliance at the dial almost immediately without overloading your local network.
