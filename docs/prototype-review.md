# Original YAML prototype review

The supplied package is archived byte-for-byte at
[`examples/legacy/mock_energy.yaml`](../examples/legacy/mock_energy.yaml).
It is reference material, not enabled by the development configuration. The
original dashboard is archived at
[`examples/legacy/mock_energy_dashboard.yaml`](../examples/legacy/mock_energy_dashboard.yaml).
This is a static logic review; the package
has not been loaded into a running Home Assistant instance in this session.

## Entity inventory

The package declares **21 entities**: seven input numbers, four input booleans,
seven template sensors, one template switch and two template numbers.
IDs below are the expected initial IDs; an existing HA registry may differ.

| Helper | Initial | Range / step |
| --- | --- | --- |
| `input_number.mock_solar_kw` | 8 kW | 0–20 / 0.1 |
| `input_number.mock_house_kw` | 2 kW | 0–20 / 0.1; excludes EV |
| `input_number.mock_battery_kw` | -2 kW | -12–12 / 0.1; positive discharge |
| `input_number.mock_battery_soc_setting` | 65% | 0–100 / 1 |
| `input_number.mock_grid_override_kw` | 0 kW | -20–20 / 0.1; positive import |
| `input_number.mock_charger_max_amps_setting` | 16 A | 6–40 / 1 |
| `input_number.mock_charger_session_amps_setting` | 0 A | 0–40 / 1 |
| `input_boolean.mock_grid_override_enabled` | off | Grid override |
| `input_boolean.mock_charger_connected` | on | EV connected |
| `input_boolean.mock_charger_enabled` | off | Charge enable |
| `input_boolean.mock_charger_force_finishing` | off | Force session finished |

| Template entity | Behavior |
| --- | --- |
| `sensor.mock_solar_power` | Solar helper passthrough, kW |
| `sensor.mock_battery_soc` | Battery SOC helper passthrough, % |
| `sensor.mock_battery_power` | Battery helper normally; inferred battery value during grid override, kW |
| `sensor.mock_charger_power` | 240 V times lesser current setting, divided by 1000, kW; gated by enabled/connected/not finishing |
| `sensor.mock_home_load` | Base home load plus EV power, kW |
| `sensor.mock_grid_power` | Forced value or home minus solar plus battery, kW |
| `sensor.mock_charger_status_connector` | Finishing / Available / Preparing / SuspendedEVSE / Charging |
| `switch.mock_charger_charge_control` | Reads/writes charger-enabled boolean |
| `number.mock_charger_maximum_current` | Reads/writes maximum-current helper, 6–40 A |
| `number.mock_charger_session_current_limit` | Reads/writes session-current helper, 0–40 A |

Numeric sensors already declare appropriate power/battery device classes and
measurement state classes. Template unique IDs match the entity object names.
There is no EV SOC helper/sensor, normalized charger-state sensor, dynamic SOC,
battery capacity, efficiency, time acceleration or reset control in this package.

## Confirmed inconsistencies

### Grid and battery signs

The comment declares positive battery power as discharge, but normal grid power
is calculated as `home - solar + battery`. It must be
`home - solar - battery` for that convention. At the supplied defaults, with
charging disabled, the package reports -8 kW grid power. Correct balance is
`2 - 8 - (-2) = -4 kW`.

Override mode also changes battery power to `forced_grid + solar - home`.
That is consistent with the package's incorrect plus-battery grid equation,
not its declared discharge-positive convention. At defaults with forced grid
0 kW it reports +6 kW battery discharge, whereas balancing a zero-grid system
would require -6 kW battery charging.

For the native model, keep manual battery power unchanged when forcing a grid
reading. Expose calculated grid, effective grid and override state separately.
This is an intentional change from the prototype's inferred-battery behavior;
do not migrate it silently. A future balancing mode, if needed, should be a
separately named control using `battery = home - solar - forced_grid`.

### Charging below the minimum

With charger enabled and connected and session current at 1–5 A, the power
sensor produces 0.24–1.20 kW while status reports SuspendedEVSE. Fix the native
model to produce zero below 6 A. Maximum and session limits must both apply.
At 6 A power is 1.44 kW; at the default maximum 16 A it is capped at 3.84 kW.

### Status priority and vocabulary

The original connector status checks finishing before disconnection. Thus an
unplugged EV can report Finishing. Use disconnection first in the new model.
Preserve the connector sensor's OCPP vocabulary for existing dashboards, and
add `sensor.mock_charger_state` with the normalized four-state contract:

| Condition, in priority order | Connector status | Normalized state |
| --- | --- | --- |
| Disconnected | Available | charger_free |
| Finished | Finishing | charger_end |
| Enabled and power flowing | Charging | charger_charging |
| Enabled but current below 6 A | SuspendedEVSE | charger_wait |
| Connected, disabled | Preparing | charger_wait |

## Migration consequences

Keep primary sensor, switch and number IDs where registry ownership allows,
including `sensor.mock_home_load` and the connector-status sensor. Native
numbers/switches replace helpers in different domains; dashboard references to
those helpers need explicit updates. Preserve the maximum-current minimum of
6 A and session minimum of 0 A. Start with the package's actual defaults.

New entities should include EV SOC control/sensor, normalized charger status,
base home load sensor, calculated grid and explicit W/sign compatibility outputs
listed in [the migration plan](migration-plan.md). An initial EV SOC default is
a new design choice, not a value recovered from this prototype.

Do not load the legacy package and native entities with the same requested IDs
at the same time during cutover. No registry migration or package activation
is performed by this documentation change.

## Dashboard review

The supplied Mock Energy Lab dashboard contains one Simulator view and four
cards: Simulation Inputs, Mock Wallbox, Simulated Telemetry, and a two-hour
power history graph. Its 18 distinct entity references all match the original
package's expected IDs. The three omitted helpers are charger enable, maximum current and session
current backing storage; the dashboard correctly uses their template controls
instead.

Keep the dashboard YAML separate from `/config/packages/`; paste it into the
Lovelace dashboard raw configuration editor or configure it as a YAML dashboard.
It is not installed or activated by archiving it here. Runtime loading and visual
rendering have not been tested in this session.

The following eight direct helper references need native replacements. These
replacement IDs are proposed and subject to registry availability.

| Existing dashboard reference | Proposed native entity |
| --- | --- |
| `input_number.mock_solar_kw` | `number.mock_solar_kw` |
| `input_number.mock_house_kw` | `number.mock_house_kw` |
| `input_number.mock_battery_kw` | `number.mock_battery_kw` |
| `input_number.mock_battery_soc_setting` | `number.mock_battery_soc_setting` |
| `input_boolean.mock_grid_override_enabled` | `switch.mock_grid_override_enabled` |
| `input_number.mock_grid_override_kw` | `number.mock_grid_override_kw` |
| `input_boolean.mock_charger_connected` | `switch.mock_charger_connected` |
| `input_boolean.mock_charger_force_finishing` | `switch.mock_charger_force_finishing` |

Preserve the other ten entity
references, including the connector sensor, when practical. Add EV SOC controls,
normalized charger status, base load and calculated grid alongside the existing
cards when those entities are implemented. Do not rewrite the archived dashboard
with entities the native integration does not yet provide.
