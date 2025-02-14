import logging
from homeassistant.helpers.entity import Entity
from .kaschuetz_api import KaschuetzAPI

_LOGGER = logging.getLogger(__name__)

# Konfiguration der Integration
def setup_platform(hass, config, add_entities, discovery_info=None):
    host = config.get("host")
    if not host:
        _LOGGER.error("Keine Host-Adresse angegeben!")
        return
    
    api = KaschuetzAPI(host)
    sensors = [
        KaschuetzSensor("Temperatur", api, "temperature", "°C"),
        KaschuetzSensor("Türstatus", api, "door_status"),
        KaschuetzSensor("Klappenposition", api, "flap_position"),
        KaschuetzSensor("Brennstatus", api, "burn_status"),
        KaschuetzSensor("Fehlermeldung", api, "error"),
    ]
    add_entities(sensors, True)

class KaschuetzSensor(Entity):
    def __init__(self, name, api, key, unit_of_measurement=None):
        self._name = name
        self._api = api
        self._key = key
        self._state = None
        self._unit_of_measurement = unit_of_measurement

    @property
    def name(self):
        return f"Kaschuetz {self._name}"

    @property
    def state(self):
        return self._state
    
    @property
    def unit_of_measurement(self):
        return self._unit_of_measurement

    def update(self):
        data = self._api.get_data()
        if data and self._key in data:
            self._state = data[self._key]
