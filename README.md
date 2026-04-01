# Kaschuetz Oven Control

Home Assistant custom integration for a Kaschuetz oven controller with adaptive burn optimization.

## Features
- UI config flow (no YAML)
- Polling via `rqType=1` with health metrics
- Optional `season_entity` support (skip polling when state is `summer`)
- Writable burn parameters (`aTemp`, `schW`, `regW`, `regP`) via UI entities
- Optimizer with cycle detection, confidence scoring, and persistence
- Diagnostics endpoint for support-friendly debugging

## Installation
1. Copy `custom_components/kaschuetz` into your Home Assistant config folder.
2. Restart Home Assistant.
3. Add integration in `Settings -> Devices & Services -> Add Integration`.

## Configuration
Required:
- `host` (IP or hostname of the oven controller)

Optional:
- `season_entity` (example: `sensor.season`)

## Entities
### Sensor
- Temperature (`Temp`, degC)
- Flap Position (`Klappe`)
- Burn Status (mapped from `state`)
- Communication Error Code (`ComError`)
- Communication Error Text (mapped)
- Connection Quality (%)
- Consecutive Failures

### Binary Sensor
- Door (on when `state == 7`)
- Communication Problem

### Number
- Active Temperature (`aTemp`)
- Closing Value (`schW`)
- Regulation Value (`regW`)
- Regulation Period (`regP`)

### Select
- Optimizer Mode (`conservative`, `balanced`, `aggressive`)

### Button
- Calculate Optimization
- Apply Optimization (Safe)
- Apply Optimization (To Device)
- Reset Optimization Data

## Services
- `kaschuetz.calculate_optimization`
- `kaschuetz.apply_optimization`
  - supports `write_to_device` and `min_confidence`
- `kaschuetz.optimize_and_apply`
  - shortcut to apply optimization with confidence gating
- `kaschuetz.reset_optimization_data`

Service UI hint (Home Assistant 2026):
- Open `Developer Tools -> Actions` (not the old Services tab)
- Search for `kaschuetz.*`

## Optimization model
- Learns from observed burn samples during normal polling
- Detects coarse burn cycles using active-state transitions
- Uses cycle stability + error ratio to calculate confidence
- Stores training data persistently across Home Assistant restarts

## State mapping
- `1` Standby
- `2` Start
- `3` Betrieb
- `4` Glutphase
- `5` Warte auf Aktiv
- `6` Ruhezustand
- `7` Fuelltuere offen
- `8` Suche Maximum
- `9` Abbrandregelung
- `10` Abbrand beendet

## Development
Local quality checks:
```powershell
python -m compileall custom_components\kaschuetz
ruff check .
pytest -q
```

CI:
- GitHub Actions workflow at `.github/workflows/ci.yml`

## Support
- Issues: https://github.com/42bios/homeassistant-kaschuetz/issues
- Repo: https://github.com/42bios/homeassistant-kaschuetz
