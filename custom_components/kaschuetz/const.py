"""Constants for the Kaschuetz integration."""

from typing import Final

DOMAIN: Final = "kaschuetz"
DEFAULT_NAME: Final = "Kaschuetz Oven"

CONF_HOST: Final = "host"
CONF_SEASON_ENTITY: Final = "season_entity"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_OPTIMIZER_MODE: Final = "optimizer_mode"
CONF_OPTIMIZER_PROFILE: Final = "optimizer_profile"
CONF_EXPERIMENTAL_AUTO_OPTIMIZE: Final = "experimental_auto_optimize"

DEFAULT_UPDATE_INTERVAL: Final = 30  # default poll interval (seconds)
MIN_UPDATE_INTERVAL: Final = 5
MAX_UPDATE_INTERVAL: Final = 300
DEFAULT_EXPERIMENTAL_AUTO_OPTIMIZE: Final = False

SERVICE_CALCULATE_OPTIMIZATION: Final = "calculate_optimization"
SERVICE_PREVIEW_ONLY: Final = "preview_only"
SERVICE_EXPORT_BURN_HISTORY: Final = "export_burn_history"
SERVICE_EXPORT_BURN_HISTORY_FILE: Final = "export_burn_history_file"
SERVICE_APPLY_OPTIMIZATION: Final = "apply_optimization"
SERVICE_RESET_OPTIMIZATION: Final = "reset_optimization_data"
SERVICE_OPTIMIZE_AND_APPLY: Final = "optimize_and_apply"

DEFAULT_A_TEMP: Final = 200
DEFAULT_SCHW: Final = 300
DEFAULT_REGW: Final = 600
DEFAULT_REGP: Final = 200

RUNTIME_COORDINATOR: Final = "coordinator"
RUNTIME_OPTIMIZER: Final = "optimizer"
RUNTIME_SAVE_OPTIMIZER: Final = "save_optimizer"
RUNTIME_ENTRY_DATA: Final = "entry_data"

CONFIDENCE_LOW: Final = "low"
CONFIDENCE_MEDIUM: Final = "medium"
CONFIDENCE_HIGH: Final = "high"
CONFIDENCE_ORDER: Final = {
    CONFIDENCE_LOW: 1,
    CONFIDENCE_MEDIUM: 2,
    CONFIDENCE_HIGH: 3,
}

OPTIMIZER_MODE_CONSERVATIVE: Final = "conservative"
OPTIMIZER_MODE_BALANCED: Final = "balanced"
OPTIMIZER_MODE_AGGRESSIVE: Final = "aggressive"
OPTIMIZER_MODES: Final = [
    OPTIMIZER_MODE_CONSERVATIVE,
    OPTIMIZER_MODE_BALANCED,
    OPTIMIZER_MODE_AGGRESSIVE,
]

OPTIMIZER_PROFILE_DEFAULT: Final = "default"
OPTIMIZER_PROFILE_FAST_HEATUP: Final = "fast_heatup"
OPTIMIZER_PROFILE_STABLE_BURN: Final = "stable_burn"
OPTIMIZER_PROFILE_EFFICIENCY: Final = "efficiency"
OPTIMIZER_PROFILES: Final = [
    OPTIMIZER_PROFILE_DEFAULT,
    OPTIMIZER_PROFILE_FAST_HEATUP,
    OPTIMIZER_PROFILE_STABLE_BURN,
    OPTIMIZER_PROFILE_EFFICIENCY,
]
