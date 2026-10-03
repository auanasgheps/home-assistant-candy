# Remote Control — Washing Machines & Washer-Dryer Combos

This page documents remote control operation, cycle configuration, washer-dryer differences, maintenance counters, error handling, and polling behaviour for Candy and Hoover washing machines and washer-dryer combos in Full Control mode.

## Remote Control Status

The appliance reports whether it currently accepts remote commands via the `WiFiStatus` field in its local status telemetry. This is exposed in Home Assistant as:

- `binary_sensor.<machine>_remote_control` (diagnostic entity, `mdi:remote`)
- The `remote_control` attribute on the main status sensor (`sensor.<machine>`)

`WiFiStatus` can report `0` (off) even while the machine is online on Wi-Fi and streaming telemetry normally. This occurs whenever the appliance is operated **physically from its front panel dial**: it stays connected to your local network and reports real-time state, but rejects incoming remote write commands until control is transferred back to the network/app position (or the running cycle completes).

### Gated Entities When Remote Control is Off

Whenever Remote Control is off (or when the appliance is powered off), all entities that send write instructions to the machine become `unavailable`:

- **Cycle control buttons**: Start, Pause, Resume, and Stop
- **Program & parameter selects**: Program, Program Type, Dry Setting, Temperature, Spin Speed, and Soil Level
- **Option switches**: Prewash, Hygiene, Steam, Anti-crease, Good Night, Extra Rinse, AquaPlus, and NFC Downloadable Programs
- **Delay start**: Delay start duration number slider
- **Diagnostic buttons**: Full Check-up and Limescale Cleaning start buttons

> [!NOTE]
> Maintenance **counter reset buttons** remain available regardless of Remote Control status because they update config-entry baseline data locally in Home Assistant without dispatching commands to the appliance hardware.

---

## Cycle Controls & Execution

Both standard washing machines and washer-dryer combos support complete 4-state cycle control:

- **Start (`button.<device>_start_wash`)**: Dispatches `Write=1&StSt=1` with all selected program, temperature, spin, soil, delay, and option parameters.
- **Pause (`button.<device>_pause_wash`)**: Pauses an active cycle (`Write=1&StSt=2`).
- **Resume (`button.<device>_resume_wash`)**: When a cycle is paused (via Home Assistant, door opening, or the physical pause button), the machine reports state `PAUSED` (`MachMd == 3`). The dedicated Resume button dispatches `Write=1&Pa=0`, continuing the cycle without resetting remaining runtime or parameters.
- **Stop (`button.<device>_stop_wash`)**: Cancels the running cycle (`Write=1&StSt=0`).

---

## Program Selection: Washing Machines vs Washer-Dryer Combos

The integration automatically adapts its entity model based on appliance capabilities:

| Feature / Capability | Standard Washing Machine | Washer-Dryer Combo (`is_washer_dryer`) |
|---|---|---|
| **Program Type Selector** | Not present | `select.<device>_program_type` (`washing`, `wash_and_dry`, `drying`) |
| **Dry Setting Selector** | Not present | `select.<device>_dry_setting` (dryness presets + timed dry) |
| **Dry Target Sensor** | Not present | `sensor.<device>_dry_target` (live active dry preset & cooldown) |
| **Program Filtering** | Shows all wash & special programs | Dynamically filtered according to active Program Type |
| **Duration Estimation** | Based on wash soil level + steam offset | Includes drying target duration in wash+dry and drying modes |
| **Scheduled Finish** | Now + delay + wash duration | Now + delay + combined wash & dry duration |

### Standard Washing Machine Operation

For standard washing machines, cycle selection is straightforward:

1. Select the desired program via `select.<device>_wash_program` (or activate a special program via `switch.<device>_special_program`).
2. Adjust temperature (`select.<device>_wash_temperature`), spin speed (`select.<device>_wash_spin_speed`), and soil level (`select.<device>_wash_soil_level`).
3. Optionally enable wash option switches (e.g. Steam, Prewash, Extra Rinse) or set a delay timer.
4. Press **Start wash**.

### Washer-Dryer Combo Operation

Washer-Dryer combo appliances provide dedicated controls to switch between washing, combined wash & dry, and standalone drying cycles (tested on the **Hoover AXI** series):

#### 1. Program Type Selection (`select.<device>_program_type`)

- **Washing (`washing`)**: Standard wash cycle. The dry setting is locked to `No dry`.
- **Wash & Dry (`wash_and_dry`)**: Seamless combined cycle that completes washing and automatically transitions into drying. The wash program selector automatically filters to only show cycles compatible with automatic drying transition (`selector_position_dry > 0`), and the dry setting defaults to `Cupboard dry`.
- **Drying (`drying`)**: Standalone dry cycle without water wash (e.g. High Heat Dry, Low Heat Dry, Wool Dry). Spin speed and temperature selectors are automatically zeroed out, and only standalone drying programs appear in the program dropdown.

#### 2. Dry Setting Selection (`select.<device>_dry_setting`)

Controls the target drying dryness level or timed duration dispatched to the machine (`Dry` wire parameter):

- **Dryness Presets**: `Cupboard dry` (`Dry=2`, standard default), `Iron dry` (`Dry=3`), or `Extra dry` (`Dry=1`).
- **Timed Drying**: `30 minutes` (`Dry=8`), `60 minutes` (`Dry=7`), `90 minutes` (`Dry=6`), or `120 minutes` (`Dry=5`).
- **`No dry` (`Dry=0`)**: Used when operating in standard `washing` mode.
- **Dynamic Safety Gating**: Selecting an incompatible wash cycle (such as Delicates or Rapid cycles that do not support drying) automatically clamps the dry setting back to `No dry`. In standalone `drying` mode, `No dry` is hidden.
- **Running Lockout**: The dry setting selector reports `unavailable` while the appliance is running (`MachMd == 2`).

#### 3. Start Command Safety on Drying Cycles

When starting a standalone drying program (`program.is_dry`), the integration automatically sets target temperature, spin speed, and soil level to `0` (`TmpTgt=0`, `SpdTgt=0`, `SLevTgt=0`), matching Simply-Fi hardware protocol requirements regardless of any previous wash selections.

#### 4. Live Telemetry: Dry Target Sensor (`sensor.<device>_dry_target`)

Reflects the machine's real-time active dry target (`DryT`), including intermediate drying phases and the drum `cooldown` phase at the end of drying.

---

## Maintenance Counters & Diagnostics

Three maintenance counters mirror the Simply-Fi app's built-in reminders. All three are driven by the **cumulative total wash cycle count** reported by the device's statistics endpoint — not by elapsed calendar time.

| Counter | Threshold | Cycle to run | Auto-reset? |
|---|---|---|---|
| **Check-up** | 100 cycles (fixed) | Full Check-up button | Yes — automatic on completion (manual button fallback) |
| **Limescale** | 85–110 cycles, based on water hardness | Limescale Cleaning button (`AUTOCLEAN`) | Yes — automatic on completion (manual button fallback) |
| **Filter** | 100 cycles (fixed) | Physical cleaning required | No — manual reset button |

### Maintenance Resets and Lifecycle

- **Full Check-up**: Resets its counter automatically when the cycle completes successfully (`CheckUpState == 2`). Home Assistant posts a completion notification matching the Simply-Fi app, clears any active check-up reminder, commits the updated `total_cycles` baseline, and resets the appliance diagnostic register. A manual reset button is also available as a fallback.
- **Limescale Cleaning**: Resets its counter automatically when the `AUTOCLEAN` cycle completes successfully (`MachMd` reaches `FINISHED1` or `FINISHED2` without errors). Home Assistant dismisses any active limescale reminder, posts a cycle completion notification (matching the Simply-Fi app), commits the updated `total_cycles` baseline, and refreshes statistics. A manual reset button is also available as a fallback.
- **Filter**: Requires manual reset. Cleaning the pump filter is a physical task without machine feedback; after cleaning, press the matching **Filter maintenance reset** button.

Each reset button writes the current `total_cycles` value into the config entry as the new baseline (`CONF_KEY_MAINTENANCE_LAST_FULL_CHECKUP` / `_LIMESCALE` / `_FILTER`). The remaining-cycles sensor is a clamp: once a counter reaches 0 it stays at 0 (and keeps re-firing its notification) on every subsequent wash until reset, rather than silently restarting.

### Maintenance Notifications

- **Due reminders**: When any maintenance counter reaches 0 remaining cycles, Home Assistant posts a persistent notification prompting you to perform the required maintenance. Messages are fully localized in your chosen language.
- **Start instructions**: When starting a Full Check-up or Limescale Cleaning cycle from Home Assistant, a notification is posted with official preparation instructions (e.g. running the drum empty, adding descaling solution).
- **Completion notices & auto-dismissal**: When a Full Check-up or Limescale Cleaning cycle finishes successfully without errors, Home Assistant posts a completion notification and automatically dismisses the active due reminder.

---

## Fault & Error Code Handling

When the appliance reports an operational fault or hardware issue (`Err` code in telemetry), Home Assistant automatically captures the error and displays a persistent notification:

- **Official troubleshooting steps**: Rather than displaying an obscure error code, the notification provides authentic vendor troubleshooting instructions extracted directly from Simply-Fi resources (e.g. checking water pressure and inlet tap, cleaning pump filter, checking drain hose, or balancing load).
- **Localized guidance**: Troubleshooting instructions match your configured appliance language (or Home Assistant language).
- **Dynamic updates**: If the machine's reported error code changes while a fault is active, the persistent notification updates in-place.
- **Automatic dismissal**: Once the issue is resolved on the appliance and the error code clears (`Err` returns to 0), Home Assistant automatically clears and dismisses the notification.
- **Universal availability**: Error notifications run for all washing machines and washer-dryers in both Read-Only and Full Control modes.
- **Washer-Dryer specific faults**: Faults such as `E12` (drying system fault) provide specific troubleshooting guidance to restart drying or verify airflow.

---

## Dashboard Integration

Ready-made control cards are provided in the [`dashboard/`](../dashboard/) directory:

- **Standard Washing Machines** ([`dashboard/washing-machine.yaml`](../dashboard/washing-machine.yaml)): Displays cycle control buttons (Start/Pause/Stop), wash program selector, temperature/spin/soil controls, and scheduled start/finish chips.
- **Washer-Dryer Combos** ([`dashboard/washer-dryer.yaml`](../dashboard/washer-dryer.yaml)): Includes all washing machine controls (with cycle Resume button) plus wash/dry mode selector (`select.<device>_program_type`), dry setting selector (`select.<device>_dry_setting`), live **Dry target** telemetry chips during active drying, dynamic washing/tumble-dryer icon transitions, and drying special programs.

---

## Polling Behaviour

The coordinator adapts its polling interval based on device reachability and write operations:

| Situation | Interval | Purpose |
|---|---|---|
| **Machine reachable (active)** | 60 s | Regular status updates during normal operation |
| **Machine unreachable / Off** | 20 s | Fast wake-up detection without overloading the network |
| **Post-command settling** | ~5 s | Settling window allowing the appliance firmware to apply changes |

### Normal and Resting Intervals

`coordinator.update_interval` adapts dynamically: 60 seconds while fetches succeed, dropping to 20 seconds once the appliance is powered off or disconnected. Connection failures are treated as "powered off" rather than errors using a synthetic offline status, ensuring fast wake-up detection when you turn on the machine.

### Post-Command Refresh

Write commands (Start, Pause, Resume, Stop, Full Check-up, Limescale Cleaning, and parameter changes) do not wait for the next scheduled poll:

1. A `write_pending` counter is incremented and coordinator listeners are notified immediately — every gated control goes `unavailable` for the duration.
2. The command is dispatched to the appliance.
3. The integration pauses 5 seconds, giving appliance firmware time to process the instruction before polling.
4. The counter is decremented; once it reaches zero, a coordinator refresh is requested, pulling the updated appliance state.
5. Overlapping commands share the counter, preventing premature unlocking while any command is still settling.

