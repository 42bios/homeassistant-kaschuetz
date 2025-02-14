# Kaschütz Ofensteuerung - Home Assistant Integration

Diese benutzerdefinierte Integration ermöglicht die Einbindung der **Kaschütz Ofensteuerung** in Home Assistant.

## 🔧 Installation über HACS
1. **HACS öffnen** → Gehe zu **HACS → Integrationen**.
2. **Benutzerdefiniertes Repository hinzufügen**:
   - Gehe zu **HACS → Drei Punkte oben rechts → Benutzerdefiniertes Repository**.
   - Füge dein GitHub-Repository hinzu:  
     ```
     https://github.com/42bios/homeassistant-kaschuetz
     ```
   - Wähle als Kategorie **Integration** und klicke auf **Hinzufügen**.
3. Suche nach **Kaschütz Ofensteuerung** in HACS und installiere die Integration.
4. **Home Assistant neustarten**, damit die Integration geladen wird.

## ⚙️ Einrichtung in Home Assistant
1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**.
2. Suche nach **Kaschütz Ofensteuerung** und füge sie hinzu.
3. Trage die **IP-Adresse** der Steuerung ein und speichere die Konfiguration.
4. Nach der Einrichtung sollten die Sensoren in Home Assistant erscheinen.

## 📡 Verfügbare Sensoren
| Sensorname       | Beschreibung                         |
|-----------------|-------------------------------------|
| `sensor.kaschuetz_temperatur` | Aktuelle Temperatur des Ofens |
| `sensor.kaschuetz_tuerstatus` | Türstatus (offen/geschlossen) |
| `sensor.kaschuetz_klappenposition` | Klappenstellung (offen/zu) |
| `sensor.kaschuetz_brennstatus` | Status der Verbrennung |
| `sensor.kaschuetz_fehlermeldung` | Fehlerstatus |

## 🛠 Fehlerbehebung
Falls die Sensoren nicht erscheinen:
- **Überprüfe die IP-Adresse** der Kaschütz-Steuerung.
- **Neustart von Home Assistant** durchführen.
- **HACS-Cache leeren** unter **Entwicklerwerkzeuge → YAML → Cache leeren**.

## 💡 Noch Fragen?
Erstelle ein Issue auf [GitHub](https://github.com/42bios/homeassistant-kaschuetz/issues) oder frage in der Home Assistant Community nach! 🚀
