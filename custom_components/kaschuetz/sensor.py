from homeassistant.helpers.entity import Entity
import requests
import logging

_LOGGER = logging.getLogger(__name__)

STATE_MAP = {
    1: "state_1",
    2: "state_2",
    3: "state_3",
    4: "state_4",
    5: "state_5",
    6: "state_6",
    7: "state_7",
    8: "state_8",
    9: "state_9",
    10: "state_10"
}


class KaschuetzOvenSensor(Entity):
    def __init__(self, host, name, sensor_type):
        self._host = host
        self._name = name
        self._sensor_type = sensor_type
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        return f"Kaschuetz {self._name}"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    def update(self):
        url = f"http://{self._host}/jsonRq"
        headers = {"Content-Type": "application/json"}

        try:
            if self._sensor_type == "temperature":
                payload = {"rqType": 1}
                response = requests.post(url, json=payload, timeout=5)
                response.raise_for_status()
                json_data = response.json()
                self._state = json_data.get("Temp", "unknown")

            elif self._sensor_type == "door_status":
                payload = {"rqType": 1}
                response = requests.post(url, json=payload, timeout=5)
                response.raise_for_status()
                json_data = response.json()
                state = json_data.get("state", None)
                self._state = "open" if state == 7 else "closed"

            elif self._sensor_type == "flap_position":
                payload = {"rqType": 1}
                response = requests.post(url, json=payload, timeout=5)
                response.raise_for_status()
                json_data = response.json()
                self._state = json_data.get("Klappe", "unknown")

            elif self._sensor_type == "burn_status":
                payload = {"rqType": 1}
                response = requests.post(url, json=payload, timeout=5)
                response.raise_for_status()
                json_data = response.json()
                state = json_data.get("state", None)
                self._state = STATE_MAP.get(state, "unknown")

            elif self._sensor_type == "error":
                payload = {"rqType": 4}
                response = requests.post(url, json=payload, timeout=5)
                response.raise_for_status()
                json_data = response.json()
                self._state = json_data.get("errorState", "none")

        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Error communicating with Kaschuetz Oven: {e}")
            self._state = "unavailable"
