# Projektdokumentation

## Einleitung

### Projektbeteiligte:
- Philipp Müller
- Cedric Hintzen

### Link zum Git Repository
- https://github.com/MPhilippGit/GPIO-Manager

### Anforderungsprofil:
- Erfassung von Sensordaten:
    - BME680
    - RCWL-0516
- Automatisierte Datenpflege:
    - Auslesen der erfassten Daten alle 5 Minuten
    - Daten, welche älter sind als 30 Tage werden automatisiert gelöscht
- Weboberfläche mit Anzeige der aktuellen Daten
- Regressionsanalyse
- Fehlerlogs (Datenbank + Sensorausfälle)

### Verwendete Technologien zur Umsetzung des Anforderungsprofils:
- Systemarchitektur:
    - mariadb - Datenbank
    - NGINX - Webserver
- Programmiersprachen:
    - Python v3.13 (Backend, Sensordaten, Datenbanktransaktionen, Regression)
    - JavaScript ES6+ (UI, Graphische Darstellung)
- Python Bibliotheken:
    - scikit-learn v1.8.0 - Regressionsanalyse
    - bme680 v2.0.0 - Sensorwerterfassung (bme680)
    - gpiozero v2.0.1 - Sensorwerterfassung (RCWL-0516)
    - gunicorn - Request verwaltung und serverprozesse
- JavaScript:
    - react v.19.2 - UI-Library
    - chart.js v.4.5.1 - Library für graphische Darstellung
    - lucide/react v0.563.0 Icon Library

## Umsetzungen der Kern-Features

### Aufbau

![Tux, the Linux mascot](./screenshots/sensorkabel.jpg)

### 1. Erfassung von Sensordaten (BME680 & RCWL-0516)
Die Erfassung der Umweltdaten erfolgt über den BME680-Sensor, dessen Rohwerte (Gaswiderstand) in einen IAQ-Score umgerechnet werden. Parallel wird über den RCWL-0516 Radarsensor die Plausibilität der Messung (Anwesenheit/Bewegung) geprüft.

Die Sensoren werden als eigenständige Skripte unter `scripts/` betrieben und geben ihre Ergebnisse als JSON über stdout aus. Das Django-Backend ruft diese Skripte per `subprocess.run()` auf und liest die JSON-Ausgabe ein. Dieser Ansatz ermöglicht es, die Pi-spezifischen Bibliotheken (`bme680`, `gpiozero`) im System-Python zu belassen, ohne sie in die Django-Virtualenv einbetten zu müssen.

**BME680 Sensorskript (`scripts/bme680_read.py`):**
```python
def resistance_to_iaq(sensor):
    if sensor.data.gas_resistance <= 0:
        return 500
    GAS_MIN = 5000
    GAS_MAX = 50000
    gas = max(min(sensor.data.gas_resistance, GAS_MAX), GAS_MIN)
    return round(500 - ((gas - GAS_MIN) / (GAS_MAX - GAS_MIN) * 500), 1)


def read_once(sensor):
    prepare_voc_read(sensor)
    start = time.perf_counter()
    while time.perf_counter() - start < 15:
        if sensor.get_sensor_data():
            temperature = round(sensor.data.temperature, 2)
            pressure = round(sensor.data.pressure, 2)
            humidity = round(sensor.data.humidity, 2)
            if sensor.data.heat_stable:
                return {
                    "temperature": temperature,
                    "pressure": pressure,
                    "humidity": humidity,
                    "voc": resistance_to_iaq(sensor),
                }
    raise IOError("Stable VOC reading not achieved within timeout")


def main():
    parser = argparse.ArgumentParser(description="Read BME680 sensor")
    parser.add_argument("--monitor", action="store_true", help="Run interactive monitoring loop")
    args = parser.parse_args()
    # ...
    if args.monitor:
        monitor(sensor)   # kontinuierlicher Stream für Debugging
    else:
        data = read_once(sensor)
        print(json.dumps(data))  # JSON-Ausgabe für subprocess-Aufruf
```

Das Skript unterstützt zwei Modi:
- **Normalmodus** (kein Flag): liest einmalig und gibt JSON aus, z. B. `{"temperature": 22.5, "pressure": 1013.25, "humidity": 48.3, "voc": 120.0}`
- **`--monitor`**: öffnet einen kontinuierlichen Ausgabestrom für manuelle Sensor-Diagnose

**RCWL Bewegungserkennung (`scripts/rcwl_detect.py`):**
```python
def main():
    parser = argparse.ArgumentParser(description="Detect motion via RCWL radar sensor")
    parser.add_argument("--duration", type=float, default=10.0, help="Seconds to wait for motion")
    parser.add_argument("--monitor", action="store_true", help="Run interactive monitoring loop")
    args = parser.parse_args()

    if args.monitor:
        monitor()
        return

    try:
        sensor = MotionSensor(5)
    except Exception as e:
        print(json.dumps({"motion_detected": False, "error": str(e)}))
        sys.exit(1)

    motion_detected = bool(sensor.wait_for_active(timeout=args.duration))
    print(json.dumps({"motion_detected": motion_detected}))
```

Ausgabe im Normalfall: `{"motion_detected": true}` oder `{"motion_detected": false}`.  
Bei Initialisierungsfehler: `{"motion_detected": false, "error": "<Fehlermeldung>"}` mit Exit-Code 1.

**Sensor-Monitoring via Management Command (`GPIO/management/commands/monitor.py`):**

Für manuelle Sensor-Diagnose steht ein Django-Command zur Verfügung, der die `--monitor`-Flags der Skripte aufruft:

```bash
python manage.py monitor bme       # BME680 Live-Stream
python manage.py monitor rcwl      # RCWL Bewegungserkennung Live
python manage.py monitor bme rcwl  # beide gleichzeitig
```

### 2. Automatisierte Datenpflege
Ein Django Management Command steuert das regelmäßige Auslesen und die persistente Speicherung der Daten. Zudem werden alte Datenstände entsprechend den Anforderungen automatisiert bereinigt. Alle dabei auftretenden Ereignisse werden in 'app.log' festgehalten. Bei Fehlern wie Abbrüchen der Datenbankverbindung oder der Sensorik generiert der Django-Logger neue Einträge über die Art der Fehler. 

**Datenbereinigung (`GPIO/models.py`):**
```python
def cleanup_entries(cls, timespan=30):
    # Entfernt Einträge, die älter als 30 Tage sind
    cutoff = timezone.now() - timezone.timedelta(days=timespan)
    result = cls.objects.filter(timestamp__lt=cutoff)
    deleted, _ = result.delete()
    return deleted
```

**Messvorgang (`GPIO/management/commands/measure.py`):**

Der Command ruft die Sensor-Skripte als Subprozesse auf und liest deren JSON-Ausgabe ein. Dadurch ist Django unabhängig von den Pi-spezifischen Bibliotheken.

```python
SCRIPTS = Path(settings.BASE_DIR) / "scripts"


class Command(BaseCommand):
    help = "Adds a sensor measurements to the database"

    def get_sensor_read(self):
        """Run bme680_read.py and return a plain dict of values."""
        result = subprocess.run(
            ["python3", str(SCRIPTS / "bme680_read.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def is_plausible(self):
        """Run rcwl_detect.py and return True if motion was detected."""
        try:
            result = subprocess.run(
                ["python3", str(SCRIPTS / "rcwl_detect.py"), "--duration", "10"],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)["motion_detected"]
        except subprocess.CalledProcessError:
            return False

    def handle(self, *args, **options):
        logger = logging.getLogger(__name__)
        try:
            data = self.get_sensor_read()
            data["is_plausible"] = self.is_plausible()
            data["timestamp"] = timezone.now()
            SensorValues.save_values(**data)
            logger.info("New data: {0} C, {1} hPa, {2} rH[%], {3} [IAQ]".format(
                data["temperature"], data["pressure"], data["humidity"], data["voc"]
            ))
        except Exception as error:
            logger.error(f"{error} database operation failed")
```

**Simulierter Messvorgang für Entwicklung (`GPIO/management/commands/simulate.py`):**

Für lokale Entwicklung ohne Hardware steht ein separater Command zur Verfügung, der synthetische Messwerte erzeugt und denselben Persistenzpfad wie `measure` nutzt:

```bash
python manage.py simulate
```

```python
class Command(BaseCommand):
    help = "Generates data for db for testing. Do not use in production."

    def simulate_gpio(self):
        return {
            "temperature": round(random.uniform(22, 24), 2),
            "voc": round(random.uniform(24000, 40000), 2),
            "humidity": round(random.uniform(40, 60), 2),
            "pressure": round(random.uniform(980, 995), 2),
            "is_plausible": True
        }
```

### 3. Datenbankstruktur

**`SensorValues`** – Sensormesswerte (`GPIO/models.py`):

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | AutoField (PK) | automatisch |
| `voc` | DecimalField (10,2) | Luftqualität (IAQ-Score) |
| `pressure` | DecimalField (10,2) | Luftdruck (hPa) |
| `temperature` | DecimalField (10,2) | Temperatur (°C) |
| `humidity` | DecimalField (10,2) | Luftfeuchtigkeit (%) |
| `is_plausible` | BooleanField | Bewegung via RCWL erkannt? |
| `timestamp` | DateTimeField | Messzeitpunkt |

**`Recordings`** – Videoaufnahmen (`GPIO/models.py`):

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | AutoField (PK) | automatisch |
| `filename` | CharField (255, unique) | Dateiname (`{timestamp}.mp4`) |
| `timestamp` | DateTimeField | Aufnahmezeitpunkt |

Die Videodateien selbst liegen im Dateisystem unter `media/videos/`. Die Tabelle speichert nur die Metadaten.

### 4. Datenbank-Schnittstelle

Die Models aus der Django-Applikation können genutzt werden um einfach Endpunkte für den Datenabruf im Frontend abzubilden.

**Abrufbare-Urls (`GPIO/urls.py`):**
Im Django-Controller lassen sich sehr einfach Endpunkte deklarieren. Die Geschäftslogik ist dabei in den GPIO-models gekapselt.

```python
urlpatterns = [
    path("", views.index, name="home"),
    path("api/temps", views.fetch_temperatures, name="temps"),
    path("api/humids", views.fetch_humidities, name="humids"),
    path("api/vocs", views.fetch_vocs, name="vocs"),
    path("api/all", views.fetch_latest, name="latest"),
    path("api/regression", views.fetch_training_data, name="regression"),
    path("logs", views.fetch_log, name="log"),
    path('predict/guests/', views.predict_persons),
]
```

**Datenbereitstellung über Views (`GPIO/views.py`):**
Die Views dienen als API-Endpunkte, welche die Daten aus der Datenbank (oder aus Log-Dateien) abrufen und für das Frontend als JSON aufbereiten. Dabei werden Django-Features wie `annotate` genutzt, um Datenstrukturen zu vereinheitlichen.

**Beispiel: Abruf der aktuellsten Messwerte (`fetch_latest`):**
```python
def fetch_latest(request):
   """Gibt die aktuellste Sensormessung als JSON zurück."""
   data = SensorValues.objects.latest("timestamp")
   result = {
      "temperature": data.temperature,
      "humidity": data.humidity,
      "voc": data.voc,
      "pressure": data.pressure,
      "is_plausible": data.is_plausible,
      "timestamp": data.timestamp
   }
   return JsonResponse(result, safe=False)
```

**Beispiel: Abruf historischer Daten mit Abstraktion (`fetch_temperatures`):**
```python
def fetch_temperatures(request):
   """Gibt die letzten 10 Temperaturmessungen zurück."""
   data = list(SensorValues.objects.annotate(
      measurement=F("temperature")
   ).values("measurement", "timestamp", "is_plausible"))
   filter_data = data[-10:]
   return JsonResponse(filter_data, safe=False)
```

**Beispiel: Log-Dateien auslesen (`fetch_log`):**
```python
def fetch_log(request):
   """Liest die app.log aus und gibt die Einträge als JSON zurück."""
   logfile = BASE_DIR / "app.log"
   logcontent = []
   with logfile.open("r") as f:
      for line in f.readlines()[::-3]:
         linefields = line.split("|")
         logcontent.append({
            "level": linefields[0].strip(),
            "timestamp": linefields[1].strip(),
            "content": linefields[2].strip()
         })
   return JsonResponse(logcontent, safe=False)
```

### 5. Regressionsanalyse

**Schnittstelle für die Regression (`GPIO/regression.py`):**
Die Ergebnisse im Frontend basieren auf einem Regressionsmodel welches mit Daten aus einer CSV-Datei angereichert wurde. Die Ergebnisse des Regressionsmodells werden über einen Api-Endpunkt ausgegeben (R-Wert, Steigung und Y-Achsenabschnitt). Über die Klasse TemperatureRegressionModel hat man Zugriff auf den Zusammenhang von VOC-Werten zur Temperatur. Zusätzlich dazu ist es möglich mithilfe des VOCRegressionModels einen Zusammenhang zwischen Anzahl an Personen und dem VOC-Wert im Raum herzustellen.

```python
class VOCRegressionModel:
    """Linear model predicting estimated persons from VOC values.

    Attributes:
        FILE_REFERENCE: Path to the CSV file used to load training data.
        df: pandas DataFrame loaded from the CSV on initialization.
        model: Fitted `LinearRegression` instance.
        r2_score: Coefficient of determination for the fit.
    """

    FILE_REFERENCE = BASE_DIR / "trainingdata" / "basedata.csv"

    def __init__(self):
        # Load training data and train the model immediately.
        self.df = pd.read_csv(self.FILE_REFERENCE)
        self.model = LinearRegression()
        self.r2_score = None
        self._train()

    def _train(self):
        X = self.df[['persons_estimated']]
        y = self.df['temperature']

        # Fit the linear model on the whole dataset.
        self.model.fit(X, y)

        # Compute predictions on the training set and store R^2 score.
        y_pred = self.model.predict(X)
        self.r2_score = r2_score(y, y_pred)
        return self

    def _voc_to_person(self):
        X = self.df[['voc_value']]
        y = self.df['persons_estimated']

        self.person_model = LinearRegression()
        self.person_model.fit(X, y)
        self.person_model.predict(X)

        return {
            "slope": self.person_model.coef_[0],
            "intercept": self.person_model.intercept_
        }

    def get_r2_scrore(self):
        # Returns the stored R^2 score (method name kept for compatibility).
        return self.r2_score

    def get_slope(self):
        # Return the learned coefficient (slope) for the single-feature model.
        return self.model.coef_[0]

    def get_intercept(self):
        # Return the learned intercept of the linear model.
        return self.model.intercept_

    def get_training_data(self):
        """Read the CSV file and return a list of simple dicts for UI display.

        Each item contains the original VOC value and the target persons value.
        """
        training_data = []
        with self.FILE_REFERENCE.open("r") as file:
            file_data = csv.DictReader(file)

            for data_row in file_data:
                training_data.append({
                    "source": data_row["persons_estimated"],
                    "target": data_row["temperature"]
                })
        return training_data

class TemperatureRegressionModel:
    """Linear model predicting temperature from VOC values.

    This class mirrors `VOCRegressionModel` but uses `temperature` as the
    target column. The API is intentionally similar to keep usage consistent.
    """

    def __init__(self):
        # Read the same training CSV used by VOCRegressionModel.
        self.df = pd.read_csv(BASE_DIR / "trainingdata" / "basedata.csv")
        self.model = LinearRegression()
        self.r2_score = None
        self._train()

    def _train(self):
        X = self.df[['voc_value']]
        y = self.df['temperature']

        self.model.fit(X, y)

        y_pred = self.model.predict(X)
        self.r2_score = r2_score(y, y_pred)

    def get_r2_scrore(self):
        # Return the stored R^2 score for the temperature model.
        return self.r2_score

    def get_slope(self):
        return self.model.coef_[0]

    def get_intercept(self):
        return self.model.intercept_

    def predict_temperature(self, person_amount):
        prediction = self.model.predict([[person_amount]])[0]

```

Die Ergebnisse dieser Analyse werden mithilfe einer View bereit gestellt und im Frontend graphisch dargestellt. Des weiteren wurde ein System implementiert um basierend auf der Gästeanzahl die geschätzte Temperatur zu ermitteln.

**Vorhersage-Logik (`frontend/utils/prediction.js`):**
```javascript
class PredictionHelper {
    constructor(slope, intercept) {
        this.slope = slope;
        this.intercept = intercept;
    }

    predict(x) {
        // Lineare Regression: y = m * x + b
        return this.slope * x + this.intercept;
    }
    /**
     * 
     * @param data array of person count from the regression data
     * @returns an array of corresponding xy-pairs to visualize the regression line  
     */
    getXYValues(data) {
        return data.map(x => [parseFloat(x), this.predict(x)])
    }
}
```

**UI-Integration der Vorhersage (`frontend/components/Prediction.jsx`):**
```javascript
const yValue = useMemo(() => {
    if (xValue === "") return "";
    let result = Math.round(slope * parseInt(xValue, 10) + intercept);
    if (result > 36) result = "36 (Maximalwert)"
    return result 
}, [xValue, slope, intercept]);
```

### 6. Weboberfläche (React Dashboard)
Das Frontend basiert auf React und ruft die aktuellen Messwerte über eine API ab, um sie visualisiert darzustellen.

**Datenabruf im Dashboard (`frontend/components/Dashboard.jsx`):**
```javascript
const fetchLatest = async (endpoint) => {
    try {
        const response = await fetch(endpoint);
        const result = await response.json();
        setLatest(result);
    } catch (error) {
        console.error(error.message);
        setLatest([]);
    }
};
```

![Dashboard](./screenshots/webinterface.png)

![Measurement](./screenshots/webinterface2.png)

### 7. Sicherheitsaufnahmen (PIR-gesteuerte Videoerfassung)

Bei erkannter Bewegung durch einen PIR-Sensor wird automatisch ein 10-Sekunden-Video über die Raspberry Pi Kamera aufgezeichnet, auf dem Dateisystem gespeichert, in der Datenbank registriert und über das Frontend abrufbar gemacht.

**Ablauf:**
```
PIR-Sensor (GPIO-Pin 4)
    ↓  Bewegung erkannt
scripts/pir_monitor.py
    ↓  startet Subprocess
python manage.py videosave
    ↓  rpicam-vid (10 Sek.)
media/videos/{timestamp}.mp4
    ↓  DB-Eintrag
Recordings-Modell
    ↓  /videos API
React Recordings-Komponente
```

**PIR-Sensor Daemon (`scripts/pir_monitor.py`):**

Der Daemon wartet kontinuierlich auf ein Signal des PIR-Sensors (GPIO-Pin 4). Bei Bewegungserkennung wird der als Argument übergebene Befehl als Subprocess gestartet. Das Skript wird über `runpir` aufgerufen und läuft im Hintergrund.

```python
from gpiozero import MotionSensor

def main():
    command = sys.argv[1:]
    pir = MotionSensor(4)

    def on_motion():
        subprocess.Popen(command)

    pir.when_motion = on_motion
    pause()
```

**Videoaufnahme (`scripts/picam_record.py`):**

Nimmt über `picamzero` ein 10-Sekunden-Video auf und speichert es unter dem übergebenen Dateipfad.

```python
from picamzero import Camera

def main():
    filepath = sys.argv[1]
    cam = Camera()
    cam.record_video(filepath, duration=10)
```

**Django Management Command `runpir` (`GPIO/management/commands/runpir.py`):**

Einstiegspunkt für den Betrieb des PIR-Daemons. Nimmt einen beliebigen Folgebefehl als Argument entgegen und übergibt ihn an `pir_monitor.py`.

```python
class Command(BaseCommand):
    help = "Run PIR motion sensor and trigger a command on detection"

    def handle(self, *args, **options):
        command = options["cmd"]
        subprocess.run(["python3", str(SCRIPTS / "pir_monitor.py"), *command])
```

**Django Management Command `videosave` (`GPIO/management/commands/videosave.py`):**

Erzeugt einen Unix-Timestamp-Dateinamen, ruft `rpicam-vid` für 10 Sekunden auf und speichert anschließend den Dateinamen mit aktuellem Zeitstempel in der Datenbank.

```python
class Command(BaseCommand):
    def handle(self, *args, **options):
        output_dir = Path(settings.MEDIA_ROOT) / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = str(timezone.now().timestamp()) + ".mp4"
        output_file = output_dir / filename

        subprocess.run(["rpicam-vid", "-t", "10000", "-o", str(output_file)], check=True)

        recording = Recordings(timestamp=timezone.now(), filename=filename)
        recording.save()
```

**Datenbankmodell (`GPIO/models.py`):**

```python
class Recordings(models.Model):
    filename = models.CharField(max_length=255, unique=True)
    timestamp = models.DateTimeField(db_column="timestamp")
```

**API-Endpunkt (`GPIO/views.py` + `GPIO/urls.py`):**

```python
# views.py
def fetch_videos(request):
    recordings = list(Recordings.objects.all().values())
    return JsonResponse(recordings, safe=False)

# urls.py
path("videos", views.fetch_videos),
```

**Frontend-Integration:**

Die React-Komponente `Recordings.jsx` ruft beim Laden den `/videos`-Endpunkt ab und rendert für jeden Eintrag eine `VideoPlayer`-Komponente mit HTML5-Videosteuerung. Die Videodateien werden über den Django-Media-Server unter `/media/videos/{filename}` bereitgestellt. Die Navigation erfolgt über die Sidebar-Schaltfläche „Security Recordings".

**Aufnahme starten:**

```bash
python manage.py runpir python manage.py videosave
```

---

## Build- & Deployment-Prozess
Um Python Backends mit Apache auszugeben benötigt es weitere Module. 

### 1) Vorbereitung & Sync
- Damit das Deployment-Skript funktioniert muss gewährleistet sein, dass ein entsprechender Ordner mit den richtigen Rechten existiert 
```bash
sudo mkdir /var/www/GPIO
sudo chown -R "$USER:$USER" /var/www/GPIO
```

### 2) Deployment Skript ausführen
- Erst muss das Skript ausführbar gemacht werden
```bash
sudo chmod +x ./deploy.sh
```
- Ausführen startet den sync Prozess 
```bash
sudo chmod +x ./deploy.sh
```

### 3) Updates 
- neue Änderung aus dem Repo pullen mit git pull
- deploy.sh ausführen
```
---
