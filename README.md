# Kaschuetz Oven Control - Home Assistant Integration

This custom integration allows you to integrate the **Kaschuetz Oven** into Home Assistant, providing convenient access to oven state, temperature, flap position, and more. It features a **UI-based config flow** for easy setup, optional **season-based** error skipping, and an **options flow** for adjusting advanced abbrand parameters.

---

## Features

- **Config Flow** – Add the oven in the Home Assistant UI, no YAML needed.
- **DataUpdateCoordinator** – Only a single request per update cycle (minimal overhead).
- **Optional Season Entity** – Skip requests/avoid errors in summer (`sensor.season`).
- **Advanced Parameters** – `aTemp`, `schW`, `regW`, `regP` can be set in an options flow.
- **Translated** – English and German translation files included.

---

## Installation

1. **Download/Clone** this repository and place the folder `kaschuetz` inside:
	custom_components/kaschuetz/

2. **Restart Home Assistant** once the files are in place.

---

## Configuration

1. **Add Integration**:
- In Home Assistant, go to **Settings → Devices & Services → Integrations**.
- Click **+ Add Integration** and search for **Kaschuetz Oven Control**.
2. **Enter Host**:
- Provide the IP/host of your Kaschuetz Oven (e.g. `192.168.34.157`).
- (Optional) Provide a `season_entity` (like `sensor.season`) if you want to skip requests during summer.
3. **Complete Setup**:
- Click **Submit**. If the connection test succeeds, your oven is added as an integration.

### Advanced Options (Abbrand Parameters)

- After the initial setup, click the **Configure** (gear icon) button on the Kaschuetz integration.
- You can edit advanced parameters:
- **aTemp** – Active Temperature
- **schW** – Schließwert
- **regW** – Regulation Value
- **regP** – Regulation Period
- These will be stored in the integration’s options. The integration may fetch the current parameters from the device (if supported) and show them as defaults.

---

## Available Sensors

Once configured, you’ll see up to **five sensors**:

| Sensor Name                          | Description                                         |
|--------------------------------------|-----------------------------------------------------|
| `Kaschuetz Temperature`             | Current oven temperature (`Temp`) in °C             |
| `Kaschuetz Door_status`             | Door state (open/closed) based on oven `state=7`    |
| `Kaschuetz Flap_position`           | Flap position (`Klappe`), e.g. 0 = open, 7 = closed |
| `Kaschuetz Burn_status`             | Numeric `state` mapped to text (e.g. 3 = Betrieb)   |
| `Kaschuetz Error`                   | Error message from the oven (`errorState`)          |

### Oven States

The oven can report these states (mapped to text in the UI):

| State | Meaning                |
|-------|------------------------|
| 1     | Standby               |
| 2     | Start                 |
| 3     | Betrieb               |
| 4     | Glutphase             |
| 5     | Warte auf Aktiv       |
| 6     | Ruhezustand           |
| 7     | Fülltür offen         |
| 8     | Suche Maximum         |
| 9     | Abbrandregelung       |
| 10    | Abbrand beendet       |

---

## Optional: Summer Skipping

If you provide a `season_entity` in the config flow (e.g. `sensor.season`), the integration checks if it’s `summer`. If so, it **skips** requests to avoid unnecessary errors (like if the oven is offline all summer).

---

## Updating Abbrand Parameters

If your Kaschuetz device supports reading/writing advanced parameters (e.g. `aTemp`, `schW`, etc.), the integration attempts to:

1. Fetch current values from `rqType=4` (example) during the **Options Flow**.
2. Let you **update** them in the same flow.  
3. **(Optionally)** send them back to the device if you extend the code with `setMenuParams`. 

---

## Contributing & Support

Feel free to open issues or pull requests on [GitHub](https://github.com/42bios/homeassistant-kaschuetz). For additional features or bug reports, please include logs and a short description of your setup.

Enjoy controlling your Kaschuetz Oven with Home Assistant! 
