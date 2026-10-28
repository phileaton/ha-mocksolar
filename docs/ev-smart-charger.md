# Using Mock Solar with EV Smart Charger

Mock Solar exposes explicit watt outputs and a charge-positive battery adapter
for [EV Smart Charger](https://github.com/antbald/ha-ev-smart-charger). Its original
kW sensors retain their units and discharge-positive battery convention.

## Entity mapping

Select **single phase** and the **generic** charger model in EV Smart Charger.
Use the actual IDs assigned by your Home Assistant registry if they have suffixes.

| EV Smart Charger input | Mock Solar entity | Unit / meaning |
| --- | --- | --- |
| Solar production | `sensor.mock_solar_power_w` | W |
| Home consumption | `sensor.mock_home_base_load_w` | W, excludes EV |
| Grid import | `sensor.mock_grid_power_w` | W, positive import, negative export |
| Home battery power | `sensor.mock_battery_power_charge_positive_w` | W, positive charge, negative discharge |
| Home battery SOC | `sensor.mock_battery_soc` | % |
| EV battery SOC | `sensor.mock_ev_battery_soc` | % |
| Measured charging power | `sensor.mock_charger_power_w` | W |
| Charger status | `sensor.mock_charger_state` | Normalized four-state vocabulary |
| Charger switch | `switch.mock_charger_charge_control` | Start/stop command |
| Charger current | `number.mock_charger_session_current_limit` | A |

The home-consumption mapping deliberately uses **base household load**. Upstream
calculates a target EV current from `production - consumption`; including EV load
in that input reduces the available budget as the charger starts. The total
household reading remains available as `sensor.mock_home_load_w` for observation.
This mapping is based on the inspected source formula and the reader/controller
contract test; automatic solar-surplus stability still needs live validation.

Keep the watt sensors configured to **W** in Home Assistant. Upstream's production,
consumption, grid and battery readers use numeric states without converting their
unit attributes. Its measured charger-power reader separately supports kW.

Also available: `sensor.mock_calculated_grid_power_w` (unforced balanced grid),
`sensor.mock_home_load_w` (total including EV), and the kW equivalents. Both
effective grid sensors expose `override_enabled` and `calculated_power_kw`.
The battery adapter exposes `positive_direction: charging`.

## Limits of the pairing

Mock Solar retains the prototype's 240 V, single-phase power model and supports
6–40 A active current. The inspected upstream version uses 230 V to calculate
current budgets and generic current commands of 6–32 A. This is a roughly 4.35%
difference in watts per amp; small import readings near a calculated solar limit
are expected. A configurable simulator voltage can be added in a later milestone.

The simulator's independent maximum current defaults to 16 A. Set
`number.mock_charger_maximum_current` to your desired test ceiling (up to 32 A for
this upstream controller). Map automation to the **session limit**, keeping that
ceiling independent. Changing the ceiling can limit actual draw below the
session setting; an enabled switch alone does not prove that power is flowing.

Manual mode keeps SOC independent of power. Enable `switch.mock_dynamic_enabled`
for automatic SOC evolution, EV target completion and empty/full home battery
limits. The simulator target is `number.mock_ev_target_soc`; match it to the
upstream target when appropriate. Upstream may stop earlier under its own policy.
The force-finished and connected controls remain available for manual scenarios.

Simulation speed accelerates only local SOC evolution. It does not accelerate
upstream command delays, debounce, time windows or scheduling. Start at 1x for
paired validation; high speeds can complete a session before an upstream control
cycle runs. Reset/reload returns to manual mode with default settings.

## What was tested

The automated contract test loads the **unmodified upstream readers, current
calculator and charger controller** against actual Mock Solar entities in an
isolated Home Assistant 2026.6.4 instance. It verifies:

- Watt readings and import/export signs.
- Both battery charge and discharge interpretation.
- Start at 16 A (3840 W), decrease to 6 A (1440 W), and stop.
- A production drop, the upstream calculator's zero-current result, and a
  controller stop followed by restart after production recovers.
- Finished and disconnected lifecycle classification.

Hardware settling and command-rate delays are set to zero for this test. HTTP
requests are blocked. The upstream integration's setup, scheduling, arbitration,
forecasting, dashboard and full solar-surplus loop are **not** loaded or tested.
This is a reader/controller contract check, not a complete end-to-end certification.

The inspected `master` source reported manifest version **2.14.0**. To identify
the exact source used, its Git blob hashes were:

| File under `custom_components/ev_smart_charger/` | Git blob SHA |
| --- | --- |
| `power_model.py` | `aca0dc27b8e4b459a72a38b5b87eef233b88406e` |
| `charger_controller.py` | `370542bb2c41204c2e0fead9b44715476c39100a` |
| `const.py` | `93f07ad0b6a4e6e3122f8289b03c95ba934efed8` |
| `utils/amperage_helper.py` | `babcb686cfefd9eb833c73ab46076ea141aeb0c6` |

Primary sources: [power readers](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/power_model.py),
[controller](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/charger_controller.py),
[solar-surplus budget](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/solar_surplus.py),
and [voltage/current constants](https://github.com/antbald/ha-ev-smart-charger/blob/master/custom_components/ev_smart_charger/const.py).

## Repeat the contract test

Keep a trusted upstream source checkout outside this repository; it is not
installed into your running Home Assistant or downloaded by the test. With this
project's development dependencies installed, run from this repository root:

```sh
MOCK_SOLAR_EVSC_PATH=/path/to/ha-ev-smart-charger \
  python3 -m unittest tests.test_ev_smart_charger -v
```

The variable accepts either the upstream repository root or its
`custom_components/ev_smart_charger` directory. The optional test imports code
from that checkout; source dependencies must be available in your test environment.
Ordinary offline tests skip this check when the variable is unset. New upstream
versions can change the contract; record the version/revision when testing them.

## Live validation checklist

Use the native dashboard to establish repeatable conditions. Start with grid
override off, battery power zero, an EV connected and not finished, and EV SOC
below EV Smart Charger's target. Match its time window and priority settings to
the scenario and allow its configured debounce/rate-limit delays to elapse.

1. Enable its solar-surplus mode with sufficient production and confirm the
   mapped session current and charger switch respond. Check measured power,
   total household load and grid exchange together.
2. Reduce solar production and observe current reduction or stop; restore it and
   observe recovery. Record the policy/settings and delays rather than assuming
   a fixed response time.
3. Test battery power in each direction and confirm the selected watt adapter
   reverses sign relative to the original kW battery sensor.
4. Unplug or mark finished; verify zero measured draw and the normalized lifecycle
   state. An external enable command must still produce zero draw while unplugged.
5. Enable grid override for an intentional import/export signal; check its
   override indication and the separate calculated grid reading.

This live checklist has not been executed against a running paired installation.
