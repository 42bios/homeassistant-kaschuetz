# Home Assistant Kaschuetz Integration 🔥

This is a **custom integration** for Home Assistant that enables communication with Kaschuetz Euromatic stoves via Wi-Fi. 

## Features 🚀

- Retrieve and display real-time stove data (temperature, flap position, state, etc.) 
*soon* - Control available functions via Home Assistant 
- Lovelace integration for easy monitoring 

## Installation 🛠️

### HACS (Recommended) 

1. Open Home Assistant. 
2. Navigate to **HACS** > **Integrations**.
3. Click on **"+"** and search for "Kaschuetz".
4. Install the integration and restart Home Assistant. 

Alternatively, you can manually add this repository as a custom repository in HACS:

- Go to HACS > Integrations > **Custom repositories** 
- Add `https://github.com/42bios/homeassistant-kaschuetz` as a **Integration** repository
- Install and restart Home Assistant 

### Manual Installation

1. Download the latest release from [GitHub](https://github.com/42bios/homeassistant-kaschuetz/releases). 
2. Extract and place the `custom_components/kaschuetz` folder into your Home Assistant `config/custom_components/` directory. 
3. Restart Home Assistant. 

## Configuration ⚙️

1. In Home Assistant, go to **Settings** > **Devices & Services**. 
2. Click on **Add Integration** and search for "Kaschuetz". 
3. Enter the IP address of your Kaschuetz stove and confirm. 

## Usage 🔥

- Once configured, the integration will create several sensors representing the stove’s state. 
- You can use these sensors in Lovelace dashboards, automations, and scripts. 

## Sensors & Attributes 

| Sensor                           | Description                          |
| -------------------------------- | ------------------------------------ |
| `sensor.kaschuetz_temperature`   | Current stove temperature            |
| `sensor.kaschuetz_flap_position` | Flap position (0=open, to 7=closed)  |
| `sensor.kaschuetz_state`         | Current operation state              |
| `sensor.kaschuetz_com_error`     | Communication error code             |

## Installation via HACS 

Easiest install is via [HACS](https://hacs.xyz/):

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=42bios&repository=homeassistant-kaschuetz&category=integration)

## Contribution 

Contributions, issues, and feature requests are welcome! Feel free to [open an issue](https://github.com/42bios/homeassistant-kaschuetz/issues) or submit a pull request. 

