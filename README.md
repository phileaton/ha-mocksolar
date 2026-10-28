# Mock Solar

Mock Solar is a planned Home Assistant energy simulator for testing automations
and integrations without physical hardware. It will expose solar production,
household load, home battery storage, grid import/export, an EV charger and an EV
battery through standard Home Assistant entities.

## Current status

This checkout contains a renamed integration blueprint, not a working energy
simulator. Its configuration flow still requests sample credentials and its
entities use JSONPlaceholder data. Do not enter real credentials.

The original YAML package is preserved unchanged at
[`examples/legacy/mock_energy.yaml`](examples/legacy/mock_energy.yaml). It has
known power-balance and charger-state inconsistencies described in the
[prototype review](docs/prototype-review.md). The [original dashboard](examples/legacy/mock_energy_dashboard.yaml) is also
preserved. Load dashboard YAML through the Lovelace dashboard editor, never
inside `/config/packages/`. Neither reference file is enabled in the development
configuration.

See [the assessment and migration plan](docs/migration-plan.md) for the inventory,
power conventions, EV Smart Charger compatibility findings and implementation steps.

## Planned first release

- UI configuration without credentials or cloud access.
- Adjustable solar production, household load, battery power and SOC.
- EV connection, charging enable/finished controls and independent current limits.
- Immediate recalculation of charger power, total household load and grid power.
- EV SOC and normalized charger status sensors for external integrations.
- Optional dashboard using native entities.

Time-based SOC, accelerated simulation and scenario presets follow the manual model.

## Development

The integration domain remains `mock_solar`; source is in
`custom_components/mock_solar/`.

- `scripts/setup`: install development dependencies.
- `scripts/develop`: start Home Assistant with the development configuration.
- `scripts/lint`: run lint tools.

These scripts currently operate on the blueprint. HACS metadata is present;
a simulator release has not yet been validated.
