# Changelog

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
