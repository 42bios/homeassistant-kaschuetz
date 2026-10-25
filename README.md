# Kaschuetz Oven Control

[![CI](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/ci.yml/badge.svg)](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/ci.yml)
[![HACS](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/validate-hacs.yml/badge.svg)](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/validate-hacs.yml)
[![Hassfest](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/hassfest.yml/badge.svg)](https://github.com/42bios/homeassistant-kaschuetz/actions/workflows/hassfest.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Version](https://img.shields.io/github/v/release/42bios/homeassistant-kaschuetz)](https://github.com/42bios/homeassistant-kaschuetz/releases)

Home Assistant custom integration for Kaschuetz oven controllers with adaptive burn optimization.

If you find this project useful, you can support its development and testing by buying me a coffee.

[![buy me a coffee – donate](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow?style=flat-square)](https://buymeacoffee.com/42bios)

<img src="https://raw.githubusercontent.com/42bios/homeassistant-kaschuetz/main/.github/images/hacs_preview.png?v=20260401-2" width="160" alt="Kaschuetz HACS Preview">

> **Disclaimer:** This is an unofficial, community-maintained integration and is not affiliated with, endorsed by, or supported by Kaschuetz. All product names, logos, and brands are property of their respective owners and are used for identification purposes only.

## Highlights
- UI config flow (`Settings -> Devices & Services`)
- Local polling of status, burn history and parameters in one request, with connection quality metrics
- Burn parameters (`aTemp`, `schW`, `regW`, `regP`) changeable from Home Assistant, saved through the controller's own save process (filling door confirmation at the oven)
- Optional season lock (`season_entity = summer` skips polling)
- Optimizer with cycle detection, KPI scoring, profile tuning, persistence
- Diagnostics endpoint for faster issue analysis
- Multilingual UI texts (`de` and `en`) for entities, states, and services

## HACS Installation (Recommended)
[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=42bios&repository=homeassistant-kaschuetz&category=integration)

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

## Saving Burn Parameters
The controller (Euromatic) only accepts new parameters through its save process, exactly like its own web interface:

1. Change one or more of the number entities. The values are only **staged** in Home Assistant (attribute `pending: true`); nothing is sent to the oven yet.
2. Press **Save parameters** (`button`) or call `kaschuetz.start_save_process`. This is only possible in the states *Waiting for active*, *Idle* or *Burn finished*.
3. Follow the **Save process** sensor: open the filling door, keep it open, close it. You have 30 seconds.
4. When the controller reports *ready*, all parameters are written together. The result is shown in the sensor and fired as event `kaschuetz_save_result`.

If the controller does not report its current parameters, nothing is written. **Cancel save process** ends a running save on the device; **Discard changed parameters** drops staged values.

| Parameter | Range | Step | Unit |
|---|---|---|---|
| Active temperature (`aTemp`) | 75 - 400 | 25 | degC |
| Closing value (`schW`) | 10 - 90 | 2.5 | % |
| Control value (`regW`) | 1 - 10 | 0.25 | % |
| Control period (`regP`) | 150 - 300 | 50 | s |

The ranges and steps are the ones the controller's web interface allows.

## Entities
### Sensor
- Temperature, flap position (% and raw 0-7)
- Burn status (see state mapping), error and error code (`errorState`)
- Save process (`idle`, `open_door`, `keep_door_open`, `close_door`, `writing`, `success`, `failed`, `timeout`, `cancelled`, ...) with remaining time and staged values as attributes
- Device parameters as reported by the controller, display language
- Communication code (`ComError`, raw), connection quality, consecutive failures, last successful poll
- Optimizer samples / cycles / confidence
- History time and KPIs from the burn history (`time_to_peak`, peak temperature, peak above active temperature, cooldown rate, flap oscillation)

### Binary Sensor
- Filling door (state `7`)
- Fault (state `11` or an error code reported)
- Communication problem (polling failed)

### Number
- Active temperature, closing value, control value, control period (staged until saved)

### Switch
- Close air shutter (on save): sent with the next save, only allowed in *Waiting for active*

### Select
- Optimizer mode (`conservative`, `balanced`, `aggressive`)

### Button
- Save parameters / Cancel save process / Discard changed parameters
- Calculate optimization
- Apply optimization (experimental, stages the suggestion)
- Apply optimization and save (experimental, stages and starts the save process)
- Reset optimization data

## Services
- `kaschuetz.start_save_process`
- `kaschuetz.cancel_save_process`
- `kaschuetz.discard_pending_parameters`
- `kaschuetz.calculate_optimization`
- `kaschuetz.preview_only` (safe recommendation preview)
- `kaschuetz.export_burn_history` (event + notification export)
- `kaschuetz.export_burn_history_file` (JSON/CSV file export)
- `kaschuetz.apply_optimization` (`start_save`, `min_confidence`; stages the suggestion)
- `kaschuetz.optimize_and_apply` (shortcut with confidence gate)
- `kaschuetz.reset_optimization_data`

Home Assistant 2026 note:
- Use `Developer Tools -> Actions` (instead of the old Services tab)
- Search for `kaschuetz.*`

## Lovelace Graph Card (Abbrandverlauf)
- Ready-to-use YAML: `docs/lovelace_abbrandverlauf.yaml`
- Requires `ApexCharts Card` (HACS Frontend)
- Requires `Config Template Card` (HACS Frontend)
- Dynamic multilingual title based on HA UI language (`de`/`en`)
- Shows last `3h` in local time (`HH:mm`, no seconds)

Preview:

![Kaschuetz Abbrandverlauf Card](https://raw.githubusercontent.com/42bios/homeassistant-kaschuetz/main/.github/images/abbrandverlauf_card.png?v=20260403-2)

Quick setup:
1. `Dashboard -> Edit -> Add Card -> Manual`
2. Paste the YAML from `docs/lovelace_abbrandverlauf.yaml`
3. Adjust entity ids if needed:
- `sensor.kaschuetz_oven_temperature`
- `sensor.kaschuetz_oven_flap_position`

## Optimization Model
- Learns from observed burn samples during normal polling
- Detects coarse burn cycles via active/inactive transitions
- Uses cycle stability + error ratio to derive confidence
- Persists learned history across Home Assistant restarts

## State Mapping
- `0` Initializing
- `5` Waiting for active
- `6` Idle
- `7` Filling door open
- `8` Searching maximum
- `9` Burn control
- `10` Burn finished
- `11` Fault
- `40` Waiting

Error codes (`errorState`): `34` fault, `35` temperature sensor, `36` air shutter, `37` power supply, `38` KS, `39` air shutter*.

## Protocol Notes
`POST http://<host>/jsonRq` with a JSON body. `rqType` is a bit mask: `1` temperature/flap, `2` burn history (240 points, 30 s apart, newest first), `4` menu parameters, `8` set menu parameters, `512` save process, `1024` re-read parameters.

## Development
```bash
pip install pytest-homeassistant-custom-component ruff
ruff check .
pytest -q
```

The tests use a simulated controller (`tests/fake_device.py`) including the save handshake.

## Releases
- Create and push a semantic tag, for example `v1.4.0`.
- The `Release` workflow will automatically publish a GitHub Release.
- Release notes are auto-generated and grouped via `.github/release.yml`.

## Support
- Issues: https://github.com/42bios/homeassistant-kaschuetz/issues
- Releases: https://github.com/42bios/homeassistant-kaschuetz/releases

## License
MIT - see [LICENSE](LICENSE).
