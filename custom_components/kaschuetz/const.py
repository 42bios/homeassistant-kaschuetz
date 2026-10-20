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
SERVICE_START_SAVE_PROCESS: Final = "start_save_process"
SERVICE_CANCEL_SAVE_PROCESS: Final = "cancel_save_process"
SERVICE_DISCARD_PENDING: Final = "discard_pending_parameters"

# jsonRq request types are a bit mask (see the device web UI, kasch_menu.html).
RQ_QUERY_TEMP: Final = 1 << 0  # Temp, Klappe
RQ_QUERY_HISTORY: Final = 1 << 1  # TempArr, KlappeArr, Time_s
RQ_QUERY_MENU_PARAMS: Final = 1 << 2  # spr, aTemp, schW, regW, regP
RQ_SET_MENU_PARAMS: Final = 1 << 3  # requires the save process to be "ready"
RQ_SAVE_PARAMS_PROCESS: Final = 1 << 9  # saveParamsActive -> saveParamsState
RQ_READ_MENU_PARAMS: Final = 1 << 10  # re-read parameters after saving

# Device writes the history ring buffer every 30 s, newest value first.
HISTORY_SAMPLE_STEP_SECONDS: Final = 30
HISTORY_BUFFER_SIZE: Final = 240

# Burn parameters in device units with the range and step the web UI allows.
BURN_PARAM_KEYS: Final = ("aTemp", "schW", "regW", "regP")
BURN_PARAM_LIMITS: Final = {
    "aTemp": (75, 400, 25),  # degC
    "schW": (100, 900, 25),  # 1/10 %
    "regW": (100, 1000, 25),  # 1/100 %
    "regP": (150, 300, 50),  # s
}
BURN_PARAM_SCALE: Final = {"aTemp": 1, "schW": 10, "regW": 100, "regP": 1}
DEVICE_PARAM_UNKNOWN: Final = -1

# Device states as shown by the web UI.
STATE_INIT: Final = 0
STATE_WAITING_FOR_ACTIVE: Final = 5
STATE_IDLE: Final = 6
STATE_DOOR_OPEN: Final = 7
STATE_SEARCHING_MAXIMUM: Final = 8
STATE_BURN_CONTROL: Final = 9
STATE_BURN_FINISHED: Final = 10
STATE_FAULT: Final = 11
STATE_WAITING: Final = 40
BURN_STATES: Final = frozenset({STATE_SEARCHING_MAXIMUM, STATE_BURN_CONTROL})
SAVE_ALLOWED_STATES: Final = frozenset(
    {STATE_WAITING_FOR_ACTIVE, STATE_IDLE, STATE_BURN_FINISHED}
)
CLOSE_AIR_SHUTTER_ALLOWED_STATES: Final = frozenset({STATE_WAITING_FOR_ACTIVE})

# Save process (the device asks the user to open and close the filling door).
SAVE_PROCESS_TIMEOUT_SECONDS: Final = 30
SAVE_PROCESS_POLL_SECONDS: Final = 1.0
SAVE_RELOAD_DELAY_SECONDS: Final = 6
SAVE_DEVICE_STATE_READY: Final = 10

SAVE_STATUS_IDLE: Final = "idle"
SAVE_STATUS_STARTING: Final = "starting"
SAVE_STATUS_WRONG_STATE: Final = "wrong_state"
SAVE_STATUS_OPEN_DOOR: Final = "open_door"
SAVE_STATUS_KEEP_DOOR_OPEN: Final = "keep_door_open"
SAVE_STATUS_CLOSE_DOOR: Final = "close_door"
SAVE_STATUS_WRITING: Final = "writing"
SAVE_STATUS_SUCCESS: Final = "success"
SAVE_STATUS_FAILED: Final = "failed"
SAVE_STATUS_TIMEOUT: Final = "timeout"
SAVE_STATUS_CANCELLED: Final = "cancelled"
SAVE_STATUSES: Final = [
    SAVE_STATUS_IDLE,
    SAVE_STATUS_STARTING,
    SAVE_STATUS_WRONG_STATE,
    SAVE_STATUS_OPEN_DOOR,
    SAVE_STATUS_KEEP_DOOR_OPEN,
    SAVE_STATUS_CLOSE_DOOR,
    SAVE_STATUS_WRITING,
    SAVE_STATUS_SUCCESS,
    SAVE_STATUS_FAILED,
    SAVE_STATUS_TIMEOUT,
    SAVE_STATUS_CANCELLED,
]
SAVE_DEVICE_STATE_TO_STATUS: Final = {
    1: SAVE_STATUS_WRONG_STATE,
    2: SAVE_STATUS_OPEN_DOOR,
    3: SAVE_STATUS_KEEP_DOOR_OPEN,
    4: SAVE_STATUS_CLOSE_DOOR,
}

EVENT_SAVE_RESULT: Final = "kaschuetz_save_result"

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
