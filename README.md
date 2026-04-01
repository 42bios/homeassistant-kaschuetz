# Kaschuetz Oven Control

[![CI](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/ci.yml/badge.svg)](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/ci.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Version](https://img.shields.io/github/v/release/42bios/homeassistant-kaschuetz)](https://github.com/42bios/homeassistant-kaschuetz/releases)

Home Assistant custom integration for Kaschuetz oven controllers with adaptive burn optimization.

![Kaschuetz HACS Preview](.github/images/hacs_preview.png)

## Highlights
- UI config flow (`Settings -> Devices & Services`)
- Local polling (`rqType=1`) with connection quality metrics
- Optional season lock (`season_entity = summer` skips polling)
- Writable burn parameters (`aTemp`, `schW`, `regW`, `regP`)
- Optimizer with cycle detection, confidence scoring, persistence
- Diagnostics endpoint for faster issue analysis

## HACS Installation (Recommended)
1. Open HACS in Home Assistant.
2. Go to `Integrations`.
3. Open menu (three dots) -> `Custom repositories`.
4. Repository URL: `https://github.com/42bios/homeassistant-kaschuetz`
5. Category: `Integration`
6. Install `Kaschuetz Oven Control` and restart Home Assistant.
7. Add integration in `Settings -> Devices & Services -> Add Integration`.

## Manual Installation
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
- Last Successful Poll
- Optimizer Samples / Cycles / Confidence

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
- `kaschuetz.apply_optimization` (`write_to_device`, `min_confidence`)
- `kaschuetz.optimize_and_apply` (shortcut with confidence gate)
- `kaschuetz.reset_optimization_data`

Home Assistant 2026 note:
- Use `Developer Tools -> Actions` (instead of the old Services tab)
- Search for `kaschuetz.*`

## Optimization Model
- Learns from observed burn samples during normal polling
- Detects coarse burn cycles via active/inactive transitions
- Uses cycle stability + error ratio to derive confidence
- Persists learned history across Home Assistant restarts

## State Mapping
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
```powershell
python -m compileall custom_components\kaschuetz
ruff check .
pytest -q
```

## Releases
- Create and push a semantic tag, for example `v1.3.1`.
- The `Release` workflow will automatically publish a GitHub Release.
- Release notes are auto-generated and grouped via `.github/release.yml`.

## Support
- Issues: https://github.com/42bios/homeassistant-kaschuetz/issues
- Releases: https://github.com/42bios/homeassistant-kaschuetz/releases
