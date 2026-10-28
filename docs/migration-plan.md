# Mock Solar assessment and migration plan

Assessment date: 2026-10-27. Local files were inspected directly. Desired behavior
comes from the supplied handoff and the subsequently supplied original YAML. Upstream findings describe EV Smart Charger's
`master` source inspected on this date, not a tested pairing with a release.

## Implementation progress

The manual model and native wiring milestones are now implemented: a validated,
immutable local model, credential-free single-instance setup, 31 native entities,
immediate command updates, blueprint entry migration, and lifecycle tests.
The optional native dashboard is `examples/mock_energy_dashboard.yaml`. SOC is
manual and inputs reset on reload/restart. W/sign compatibility outputs are
implemented and the actual upstream readers/controller have passed an optional
contract test. Full scheduling and solar-surplus arbitration still require live
validation; see [the mapping and test guide](ev-smart-charger.md). Elapsed-time
simulation is the next implementation milestone. See the README for current installation and controls.

The inventory below records the original blueprint assessment. Sample API,
polling, credentials and example entities have since been replaced; simulation,
number, strings and test files now exist.

## Original inventory and gaps

| Files | Current behavior |
| --- | --- |
| `manifest.json` | Mock Solar name/domain and repository links; still cloud polling and template codeowner |
| `__init__.py`, `data.py`, `coordinator.py` | Runtime data, hourly sample API polling, platform setup and unload |
| `api.py` | GET/PATCH of JSONPlaceholder post 1; credentials are stored but not used to authenticate |
| `config_flow.py`, `translations/en.json` | Username/password form, sample connectivity check, username-derived identity |
| `sensor.py` | One Integration Sensor returning the sample post body |
| `switch.py` | One Integration Switch patching the sample post title |
| `binary_sensor.py` | One Mock Solar Binary Sensor comparing the post title |
| `entity.py` | Shared device identity, sample attribution and unique ID without an entity-specific key |
| `config/configuration.yaml` | Development HA configuration and logging; no simulator package |
| `hacs.json`, scripts, requirements, workflows | Template development/distribution scaffolding |

Integration filenames above are relative to `custom_components/mock_solar/`.
The original prototype package is now archived unchanged at
`examples/legacy/mock_energy.yaml`; see [the prototype review](prototype-review.md)
for its complete entity inventory and inconsistencies. The original dashboard is
archived at `examples/legacy/mock_energy_dashboard.yaml`; all 18 distinct entity
references match the package's expected IDs. At the time of the original assessment, the simulation engine, native number
platform, strings.json and test suite were absent. These are now implemented.
Actual example entity IDs depend on the Home Assistant entity registry and cannot
be established from this checkout.

The sample switch also reverses its reported state: turn-on writes `bar`, while
`is_on` checks for `foo`. This should be replaced by shared local simulation state.
The remote example API cannot serve as simulator state storage.

## Power model and state contract

Retain the prototype convention internally and on its primary sensors:

```text
permitted_current_a = min(maximum_current_a, session_current_limit_a)
charger_power_kw = voltage_v * actual_current_a / 1000
total_home_load_kw = base_home_load_kw + charger_power_kw
calculated_grid_power_kw = total_home_load_kw - solar_kw - battery_power_kw
```

Actual current is zero unless connected, enabled, not finished, and permitted
current is at least 6 A. Active current is limited to 40 A. Accept zero as a stop
request; 1–5 A must never produce active charging. Initial voltage is 240 V.

Battery: positive discharge, negative charge. Grid: positive import, negative
export. The handoff example is correct: `(2 + 4) - 8 - (-1) = -1 kW` (1 kW export).
Keep calculated grid power visible separately from forced grid power, with an
explicit override switch. Forced readings must not silently redefine the balance.

Status priority:

1. Disconnected: `charger_free`.
2. Finished: `charger_end`.
3. Enabled with positive charging power: `charger_charging`.
4. Otherwise: `charger_wait`.

SOC controls must stay within 0–100%. Manual mode deliberately allows independent
SOC and power settings for reproducible tests; physical empty/full battery limits
and elapsed-time integration belong to the later dynamic model.

## EV Smart Charger compatibility checks

Inspected primary source:

- [Power readers and status handling](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/power_model.py)
- [Numeric state helper](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/utils/state_helper.py)
- [Charger command adapter](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/charger_controller.py)
- [Entity selectors](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/config_flow.py)
- [Voltage, amperage and status constants](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/const.py)
- [Solar surplus calculation](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/solar_surplus.py)

| Input | Source behavior | Migration consequence |
| --- | --- | --- |
| Solar / home / grid power | Numeric readings treated as W; no charger reader's explicit kW conversion | Provide W compatibility sensors |
| Battery power | Negative discharge, positive charge; discharge is clamped negation of numeric state | Provide separate W sensor equal to `-1000 * battery_power_kw` |
| Charger power | Explicit kW-to-W conversion supported | Existing kW model can work; W output is useful for consistent mapping |
| Grid direction | Positive import | Matches prototype |
| Charger status | Recognizes the four proposed strings and additional brand vocabulary | Use normalized four-state sensor |
| Current control | Supports number/input_number/select/input_select; native number uses set_value | Map session current limit; keep maximum current as independent ceiling |
| SOC | Sensor entities accepted | Expose percent, battery device class and measurement state class |
| Generic current / voltage | 6–32 A and 230 V single phase | Document mismatch with simulator's 40 A / 240 V; consider configurable voltage |

Solar surplus uses production minus mapped home consumption. Expose both base
and total home load and verify the chosen mapping in an end-to-end test before
claiming compatibility. UI entity selection alone is not a compatibility test.

## Intended primary entity IDs

The original package defines the primary entities below except
`sensor.mock_ev_battery_soc` and `sensor.mock_charger_state`, which are proposed
additions. It also defines `sensor.mock_home_load` and the OCPP-style
`sensor.mock_charger_status_connector`. IDs are expected defaults, subject to
Home Assistant registry assignments.

| Entity | Contract |
| --- | --- |
| `sensor.mock_solar_power` | kW production |
| `sensor.mock_battery_soc` | % home battery SOC |
| `sensor.mock_battery_power` | kW, positive discharge |
| `sensor.mock_grid_power` | kW, positive import, explicit override indication |
| `sensor.mock_charger_power` | kW EV draw |
| `sensor.mock_ev_battery_soc` | % EV SOC |
| `sensor.mock_charger_state` | Four normalized states |
| `switch.mock_charger_charge_control` | Charge enable |
| `number.mock_charger_maximum_current` | A hardware ceiling |
| `number.mock_charger_session_current_limit` | A automation limit |

Preserve `sensor.mock_charger_status_connector` with OCPP-style vocabulary for
existing consumers; add the normalized four-state sensor separately, not as a
replacement with different vocabulary. Add numbers for solar, base load,
battery power and both SOC controls; switches for plugged-in and finished.
Native entities cannot retain input_number/input_boolean domains: document those
helper migrations and update dashboard references explicitly.

Use stable entry-plus-entity-key unique IDs and retain domain `mock_solar`.
Existing YAML entities or registry entries may already own requested IDs. Cut
over one owner at a time; do not automatically reassign registry entries.
Provide explicit W compatibility outputs without silently changing primary units
or the prototype battery sign.

## Incremental implementation sequence

1. **Review the prototype.** The package has been recovered and its IDs, defaults,
   ranges and logic reviewed in [the prototype review](prototype-review.md).
   Correct the documented sign and subminimum-current defects in the new model.
   The dashboard has also been recovered and its entity references checked.
   Preserve its four cards and migrate helper references explicitly, as detailed
   in the prototype review. Keep dashboard YAML outside packages.
2. **Test a pure manual model.** Add simulation.py independent of HA. Cover the
   export example, both current limits, zero/subminimum current, disabled,
   unplugged and finished cases, status priority, SOC bounds and grid override.
3. **Wire native entities.** Replace sample cloud behavior with central local
   state and immediate shared updates. Remove credentials; add UI setup,
   numbers, switches, derived sensors and connection binary sensor. Update
   manifest, translations, attribution and metadata together. Verify setup,
   external service commands, entity updates and unload.
4. **Verify compatibility and cut over.** Add explicit W/sign adapters. Test
   EV Smart Charger enable/disable and current commands using simulator entities,
   solar drop/recovery and grid direction. Resolve registry collisions and
   dashboard mappings. Define restart behavior before declaring stability.
5. **Add dynamic simulation.** Integrate actual elapsed time, capacities,
   efficiency, target SOC and simulation speed. Add reset and a persistence
   policy, enforce energy bounds and clean up timers on unload. Test energy
   conservation and target transitions deterministically.
6. **Prepare distribution.** Validate ownership, HACS metadata, release version,
   optional dashboard and installation on a clean Home Assistant instance.

Milestones 1–3 are complete for the manual simulator, including recovery of both
legacy files. Step 4 now includes W/sign adapters, verified upstream reader and
controller contracts, and documented entity mappings. Live scheduling/arbitration
verification remains open. Continue with the dynamic model while preserving that
validation boundary. The legacy artifacts remain unchanged.
