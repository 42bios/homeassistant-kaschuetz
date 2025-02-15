import requests
import logging

_LOGGER = logging.getLogger(__name__)

class KaschuetzAPI:
    """API-Klasse zum Abrufen von JSON-Daten der Kaschütz Ofensteuerung."""
    
    def __init__(self, host):
        self._host = host.rstrip('/')  # Sicherstellen, dass keine doppelte Slash entsteht
        self._json_url = f"{self._host}/jsonRq"
    
    def get_data(self):
        """Abrufen und Parsen der JSON-Daten von der Steuerung."""
        try:
            headers = {"Content-Type": "application/json"}
            payload = {"rqType": 1}  # Anfrage für Temperaturdaten
            response = requests.post(self._json_url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            json_data = response.json()
            
            data = {
                "temperature": json_data.get("Temp", "-"),
                "door_status": json_data.get("LANG_FÜLLTÜROFFEN", "-"),
                "flap_position": json_data.get("LANG_KLAPPEOFFEN", "-"),
                "burn_status": json_data.get("state", "-"),
                "error": json_data.get("errorState", None),
            }
            return data
        except requests.RequestException as e:
            _LOGGER.error(f"Fehler beim Abrufen der Kaschütz-Daten: {e}")
            return None
