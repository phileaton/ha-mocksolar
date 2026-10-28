# Mock Solar

Mock Solar is a local Home Assistant energy simulator for testing automations
without physical hardware. This project is a work in prograss and is being mostly vibe coded. The first implementation provides a manual solar,
household load, home battery, grid and EV charger model through **24 native
entities**. It does not connect to real devices or external APIs.

## Install and configure

1. Copy `custom_components/mock_solar` into your Home Assistant configuration's
   `custom_components` directory, then restart Home Assistant.
2. Open **Settings → Devices & services → Add integration → Mock Solar** and
   confirm creation. No credentials are required. One simulator is supported.
3. Open the Mock Solar device to adjust the numbers and switches, or use the
   [optional dashboard](examples/mock_energy_dashboard.yaml). Paste that YAML
   into a dashboard's raw configuration editor, outside `/config/packages/`.

For development in the supplied environment, install `requirements_dev.txt` and
run `bash scripts/develop`. HACS publishing and clean-install release validation
remain future work; this is a development implementation.

## Manual controls

| Control | Default | Range / behavior |
| --- | --- | --- |
| `number.mock_solar_kw` | 8 kW | 0–20 kW solar production |
| `number.mock_house_kw` | 2 kW | 0–20 kW household load excluding EV |
| `number.mock_battery_kw` | -2 kW | -12–12 kW; positive discharge, negative charge |
| `number.mock_battery_soc_setting` | 65% | 0–100% home battery SOC |
| `number.mock_grid_override_kw` | 0 kW | -20–20 kW forced grid reading |
| `number.mock_charger_maximum_current` | 16 A | 6–40 A hardware ceiling |
| `number.mock_charger_session_current_limit` | 0 A | 0–40 A external automation limit |
| `number.mock_ev_soc_setting` | 50% | 0–100% EV SOC |
| `switch.mock_charger_charge_control` | off | Enable charging |
| `switch.mock_charger_connected` | on | EV plugged in |
| `switch.mock_charger_force_finishing` | off | Session finished |
| `switch.mock_grid_override_enabled` | off | Use forced grid reading |

Commands immediately update all dependent telemetry. Current is the lesser of
the two limits; charging draws no power if disconnected, disabled, finished or
below 6 A. EV power is calculated at 240 V single phase.

## Telemetry and conventions

All power sensors use kW; both SOC sensors use percent with battery device class.

- `sensor.mock_solar_power`, `sensor.mock_home_base_load`, `sensor.mock_home_load`
- `sensor.mock_battery_power`, `sensor.mock_battery_soc`
- `sensor.mock_grid_power`, `sensor.mock_calculated_grid_power`
- `sensor.mock_charger_power`, `sensor.mock_ev_battery_soc`
- `sensor.mock_charger_state`, `sensor.mock_charger_status_connector`
- `binary_sensor.mock_ev_connected`

```text
EV power = 240 × permitted current / 1000
Total home load = base home load + EV power
Calculated grid power = total home load - solar power - battery power
```

Grid power is positive for import and negative for export. The defaults produce
**-4 kW export**. Enabling grid override changes only the effective grid reading;
it leaves battery power and calculated grid power intact. The grid sensor also
exposes `override_enabled` and `calculated_power_kw` attributes.

| Condition, in priority order | Normalized charger state | Connector state |
| --- | --- | --- |
| Unplugged | `charger_free` | Available |
| Finished | `charger_end` | Finishing |
| Drawing power | `charger_charging` | Charging |
| Enabled with insufficient current | `charger_wait` | SuspendedEVSE |
| Connected but disabled | `charger_wait` | Preparing |

SOC is manually adjustable; it does not advance or stop charging automatically.
**Reloading the integration or restarting Home Assistant resets all inputs to
these defaults.** Capacities, efficiency, target SOC, persistence, accelerated
time and scenario resets are deferred to the dynamic simulation milestone.

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

Normalized status, charger switch and current controls are implemented, but the
pairing has not been tested end to end. Its inspected source expects watts for
solar/home/grid inputs and the opposite battery-power sign. Do not directly map
these kW outputs to those watt inputs. Explicit compatibility outputs and tested
mappings are the next milestone. Its 230 V / 32 A control model also differs from
this simulator's 240 V / 40 A range. See [the migration plan](docs/migration-plan.md).

## Validation

With the development dependencies installed and Python 3.14:

```sh
python3 -m unittest discover -s tests -v
ruff check .
ruff format . --check
```

Tests run the model and real Home Assistant 2026.6.4 platforms using temporary
configuration directories. They cover power balance, status priority, bounds,
external service commands, metadata, ID collisions, sample-entry migration and
unload/reload, with HTTP requests blocked during integration operations.
