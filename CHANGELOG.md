# Changelog

## 1.4.0 - 2026-04-02

### Added
- Full burn history diagnostics based on device chart data (`TempArr`, `KlappeArr`, `Time_s`).
- New KPIs:
  - `time_to_peak_s`
  - `peak_temp`
  - `overshoot`
  - `cooldown_rate_c_per_min`
  - `flap_oscillation`
- New diagnostic sensors for SPR text mapping, history time, and KPI values.
- New services:
  - `kaschuetz.preview_only`
  - `kaschuetz.export_burn_history`
  - `kaschuetz.export_burn_history_file` (JSON/CSV to `/config/kaschuetz_exports`)
- Per-cycle curve extraction (`recent_cycle_series`) for future burn-curve analytics.
- New optimizer profile option (`default`, `fast_heatup`, `stable_burn`, `efficiency`).

### Changed
- Polling now prefers `rqType=5` with fallback to `rqType=1`.
- Optimizer now combines sample heuristics with history KPI-based adjustments.
- Preview output now includes KPI and applied adjustment reasons.
- Experimental apply behavior remains gated behind `experimental_auto_optimize`.

### Fixed
- Extended diagnostic code translation fallback for `errorState` and `spr` codes.
- Improved optimizer state persistence by storing history snapshot and KPIs.

## 1.3.0 - 2026-04-01

### Added
- New entity platforms: `binary_sensor`, `number`, `select`, and `button`.
- Optimizer workflow services:
  - `kaschuetz.calculate_optimization`
  - `kaschuetz.apply_optimization`
  - `kaschuetz.optimize_and_apply`
  - `kaschuetz.reset_optimization_data`
- Shared data coordinator with connection quality metrics and diagnostics support.
- New optimizer diagnostics sensors (samples, cycles, confidence, last successful poll).
- CI baseline with `ruff`, `pytest`, and GitHub Actions workflow.

### Changed
- Migrated device communication to async HTTP helper module.
- Improved config flow host normalization and JSON mime-type compatibility (`text/json`).
- Added optimizer mode handling (`conservative`, `balanced`, `aggressive`).
- Updated docs for Home Assistant 2026 developer tools and action usage.

### Fixed
- Resolved Home Assistant manifest parsing issues caused by BOM encoding.
- Improved compatibility for button/number entity descriptions in latest HA core.
