# Mock Solar

Mock Solar is a local Home Assistant energy simulator for testing automations
without physical hardware. This project is a work in prograss and is being mostly vibe coded. The integration models solar production, household load, home battery storage,
grid exchange and EV charging in manual or dynamic mode through **33 native
entities**. It does not connect to real devices or external APIs.

## Install and configure

1. Copy `custom_components/mock_solar` into your Home Assistant configuration's
   `custom_components` directory, then restart Home Assistant.
2. Open **Settings → Devices & services → Add integration → Mock Solar** and
   leave **Create Energy Lab dashboard** checked and confirm creation.
   No credentials are required. One simulator is supported.
3. Open **Energy Lab** in the sidebar, or use the Mock Solar device's controls.

For an existing installation, open **Settings → Devices & services → Mock Solar →
Configure** and enable **Create Energy Lab dashboard**. Changing this option
creates the dashboard without resetting the running simulation. Existing entries
start with dashboard creation disabled until you opt in.

The generated dashboard is a standard editable Home Assistant dashboard. Its
layout is bundled with the integration and its entity references use your actual
registry IDs, including suffixes. No separate YAML installation is required.
Reloads, restarts and upgrades preserve dashboard edits. After renaming an
entity, update its dashboard reference yourself or regenerate the default layout.

Use **Regenerate dashboard** on the dashboard (with a confirmation prompt), or
`button.mock_regenerate_dashboard` on the device, to explicitly replace the
layout with the bundled default and current entity IDs. This replaces your
layout edits; the device button and service call do not show a confirmation.
It does not reset simulator values. Dashboard creation must be enabled first.

Disabling dashboard creation or removing the integration leaves an existing
dashboard intact. To remove it, use Home Assistant's dashboard settings. Disable
creation first if you want it to stay deleted after a reload. Existing dashboards
at the default URL are preserved; Mock Solar chooses a different URL when needed.

The [manual dashboard YAML](examples/mock_energy_dashboard.yaml) remains an
alternative. Paste it into a dashboard's raw configuration editor, outside
`/config/packages/`, and adjust IDs if needed. It is independent of the generated
dashboard and is never changed by regeneration.

For development in the supplied environment, install `requirements_dev.txt` and
run `bash scripts/develop`. HACS publishing and clean-install release validation
remain future work; this is a development implementation.

## Manual controls

| Control | Default | Range / behavior |
| --- | --- | --- |
| `number.mock_solar_kw` | 8 kW | 0–20 kW solar production |
| `number.mock_house_kw` | 2 kW | 0–20 kW household load excluding EV |
| `number.mock_battery_soc_setting` | 65% | 0–100% home battery SOC |
| `number.mock_charger_maximum_current` | 16 A | 6–40 A hardware ceiling |
| `number.mock_charger_session_current_limit` | 0 A | 0–40 A external automation limit |
| `number.mock_ev_soc_setting` | 50% | 0–100% EV SOC |
| `switch.mock_charger_charge_control` | off | Enable charging |
| `switch.mock_charger_connected` | on | EV plugged in |
| `switch.mock_charger_force_finishing` | off | Session finished |

Battery and grid power are not controls: they are calculated from solar
production, home load and EV power. Commands immediately update all dependent telemetry. Current is the lesser of
the two limits; charging draws no power if disconnected, disabled, finished or
below 6 A. EV power is calculated at 240 V single phase.

## Telemetry and conventions

The original power sensors use kW; compatibility outputs use W. Both SOC
sensors use percent with battery device class.

- `sensor.mock_solar_power`, `sensor.mock_home_load` (including EV)
- `sensor.mock_battery_power`, `sensor.mock_battery_soc`
- `sensor.mock_grid_power`
- `sensor.mock_charger_power`, `sensor.mock_ev_battery_soc`
- `sensor.mock_charger_state`, `sensor.mock_charger_status_connector`
- `binary_sensor.mock_ev_connected`

```text
EV power = 240 × permitted current / 1000
Total home load = home load (excluding EV) + EV power
Battery power = total home load - solar power, limited to ±12 kW
Grid power = total home load - solar power - battery power
```

Battery power is positive when discharging and negative when charging. The
battery absorbs any surplus or deficit up to 12 kW, and stops at 0% (discharge)
or 100% (charge) SOC. Grid power is positive for import and negative for export;
it covers only what solar and the battery cannot. The defaults produce a
**-6 kW** battery charge and **0 kW** grid exchange.

| Condition, in priority order | Normalized charger state | Connector state |
| --- | --- | --- |
| Unplugged | `charger_free` | Available |
| Finished | `charger_end` | Finishing |
| Drawing power | `charger_charging` | Charging |
| Enabled with insufficient current | `charger_wait` | SuspendedEVSE |
| Connected but disabled | `charger_wait` | Preparing |

## Dynamic simulation

Manual mode is the default and preserves independent SOC/power controls. Turn on
`switch.mock_dynamic_enabled` to update SOC from elapsed time, with one update
per real second. These additional controls configure the model:

| Control | Default | Range / behavior |
| --- | --- | --- |
| `number.mock_battery_capacity_kwh` | 13.5 kWh | 1–100 kWh home battery capacity |
| `number.mock_ev_capacity_kwh` | 80 kWh | 1–200 kWh EV battery capacity |
| `number.mock_ev_charging_efficiency` | 95% | 1–100% of charger energy stored in EV |
| `number.mock_ev_target_soc` | 80% | 0–100% charging target |
| `number.mock_simulation_speed` | 1 | 1–3600 times real elapsed time |
| `number.mock_forecast_daily_kwh` | 30 kWh | 0–200 kWh forecast for today; drives the `sensor.mock_forecast_*` sensors (total, produced so far, remaining today, power now) using a 06:00–18:00 half-sine curve in local time |
| `number.mock_forecast_remaining_percent` | 100 % | 0–100 % of the daily forecast still to come; used only while `switch.mock_forecast_override_enabled` is on, otherwise remaining energy follows the clock |
| `button.mock_reset_simulator` | — | Restore every default and return to manual mode |

For a quick session, set the session limit to 16 A, enable charging, set speed
to 60 and enable dynamic mode. One real minute represents one simulated hour:
at 3.84 kW and 95% efficiency, an 80 kWh EV gains 4.56 percentage points of SOC
unless it reaches its target first.

In dynamic mode:

- EV charging stops at target SOC and reports `charger_end` / Finishing. The
  charge-enable switch remains on, representing the commanded permission.
- Raising the target above current SOC or lowering SOC allows charging to resume
  if connected and enabled. The force-finished switch remains a separate manual
  override and is not switched on by automatic completion.
- Home battery power stops at 0% while discharging or 100% while charging. The
  battery power sensors show zero flow and the grid covers the remainder.
  Reversing direction permits flow again.
- Home battery storage is ideal (100% efficient); EV efficiency applies only to
  energy entering the EV battery. Grid balance always uses actual power.
- Turning dynamic mode off freezes both SOC values and restores unrestricted
  manual power behavior. Time spent in manual mode is not replayed on resume.
- Power, capacity, efficiency and speed commands settle the preceding interval
  under its old settings before applying the change. Delayed timer callbacks
  use actual monotonic elapsed time, rather than assuming exactly one second.

SOC can still be adjusted directly for testing. This is a constant-power model
with instantaneous stop at energy limits; it does not model charging taper,
weather curves or inverter control. Accelerated time affects only Mock Solar's
SOC evolution, not other integrations' debounce, scheduling or rate limits.

**Reloading the integration or restarting Home Assistant resets all inputs to
the defaults and starts in manual mode.** There is no persistence or simulation
of time spent offline. Use the reset button to repeat a scenario without reload.

## Migrating the YAML prototype

The [original package](examples/legacy/mock_energy.yaml) and
[original dashboard](examples/legacy/mock_energy_dashboard.yaml) are preserved
unchanged. The native model fixes their grid sign and subminimum-current bugs;
see [the prototype review](docs/prototype-review.md).

Remove the old package's entity definitions and restart before native setup if
you want the original IDs. Existing entity registry entries can still reserve
IDs; inspect assignments and update dashboard/automation references as needed.
The integration respects existing ownership and may receive suffixed IDs.
Helper controls change from `input_number`/`input_boolean` to `number`/`switch`;
the native dashboard already uses the new references. Existing blueprint config
entries upgrade automatically and discard unused sample credentials. Old sample
entities may remain as unavailable registry entries and can be removed manually.

## EV Smart Charger

Seven compatibility sensors now expose W readings, including an explicitly named
charge-positive battery adapter. The original kW sensors retain their conventions.
See the [mapping and testing guide](docs/ev-smart-charger.md) for exact entity
selections, current/voltage limits and a live validation checklist.

The real upstream readers and charger controller were tested against Mock Solar
entities. Full scheduling and solar-surplus arbitration remain unverified.

## Validation

With the development dependencies installed and Python 3.14:

```sh
python3 -m unittest discover -s tests -t . -v
ruff check .
ruff format . --check
```

Tests run the model and real Home Assistant 2026.6.4 platforms using temporary
configuration directories. They cover power balance, status priority, bounds,
external service commands, metadata, ID collisions, sample-entry migration and
unload/reload, watt/sign adapters, dynamic energy limits, accelerated time,
reset, a real Home Assistant timer callback, and real Lovelace dashboard
creation/preservation/regeneration, with HTTP requests blocked during integration
operations. An optional [upstream contract test](docs/ev-smart-charger.md#repeat-the-contract-test)
runs against an external EV Smart Charger source checkout; it is skipped unless
`MOCK_SOLAR_EVSC_PATH` is set.
