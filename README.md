# ZESCO DLR Digital Twin

A **Dynamic Line Rating (DLR)** digital-twin prototype for overhead transmission
lines, built around the **IEEE Std 738** steady-state heat balance:

```
Q_joule = Q_convective + Q_radiative
```

The system ingests live telemetry from an **ESP32 sensor node**, runs the thermal
model both **forwards** (predict conductor temperature) and **backwards** (solve
the dynamic ampacity under live wind/ambient conditions), and surfaces everything
on a real-time operator dashboard.

```
┌─────────────┐   HTTPS POST   ┌──────────────────────┐   SQLite   ┌────────────┐
│   ESP32     │ ─────────────▶ │  Flask Backend        │ ─────────▶ │ telemetry  │
│ sensor node │  /api/telemetry│  + IEEE 738 engine    │            │   + events │
└─────────────┘                └──────────┬───────────┘            └────────────┘
                                          │  GET /api/...
                                          ▼
                                  ┌──────────────────────┐
                                  │  Operator Dashboard  │
                                  │  (HTML/CSS/JS charts)│
                                  └──────────────────────┘
```

## Features

- **ESP32 firmware** reading DS18B20, DHT22, ACS712 and an anemometer, posting JSON
  telemetry every second.
- **IEEE 738 engine** (`dlr_engine.py`) — forward temperature prediction, backward
  dynamic ampacity, **thermal sag & ground clearance** estimation (catenary model).
- **Flask REST API** with automatic Swagger docs at `/docs`:
  - `POST /api/telemetry` — ESP32 ingestion
  - `POST /api/demo/telemetry` — simulator injection
  - `GET /api/telemetry/latest`, `/api/telemetry/history`, `/api/telemetry/events`
  - `GET /api/dlr/rating`, `/api/dlr/calculate`, `/api/dlr/sag`
  - `GET /api/forecast` — 24 h dynamic-rating outlook
  - `GET /api/telemetry/export` — CSV download
- **SQLite persistence** of telemetry history and an **alert/event log**
  (OK / WARNING / CRITICAL with automatic event deduplication).
- **Dark-mode operator dashboard** (vanilla HTML/CSS/JS + Chart.js):
  - Live metric cards, capacity / thermal / sag charts and a 24 h forecast chart
  - Interactive simulator panel with **auto-stream** mode
  - Overload banners and a live event feed
- **Render-ready**: `render.yaml` + `gunicorn` for one-click cloud deployment.

## Quick start (local)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 (dashboard) and http://localhost:5000/docs (API docs).
On first start the app seeds ~90 minutes of demo telemetry so the charts are live
immediately — use the simulator panel to inject readings.

## Hardware / ESP32

1. Open `firmware/esp32_dlr.ino` in the Arduino IDE.
2. Install the required libraries (see header comment).
3. Set your Wi-Fi credentials and the `serverUrl`.
4. Flash and watch the serial monitor — telemetry posts every second.

For a locally running backend use `http://<your-PC-LAN-IP>:5000/api/telemetry`;
for the Render deployment use your Render service URL.

## Deploy to Render

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, select the repo — it will pick up `render.yaml`.
3. Or: **New → Web Service**, runtime *Python 3*, build command
   `pip install -r requirements.txt`, start command
   `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`,
   health check `/api/health`.

Then point the ESP32 `serverUrl` at `https://<service-name>.onrender.com/api/telemetry`.

## Project layout

```
.
├── app.py               # Flask backend + REST API
├── dlr_engine.py        # IEEE 738 physics / digital twin engine
├── database.py          # SQLite persistence
├── render.yaml          # Render blueprint
├── requirements.txt
├── templates/index.html # Dashboard page
├── static/css/style.css # Dashboard styling
├── static/js/app.js     # Dashboard logic
├── firmware/esp32_dlr.ino
└── data/                # SQLite database (git-ignored)
```

## Disclaimer

Proof-of-concept for the ZESCO Grid Innovation agenda. The thermal model is a
simplified IEEE 738 implementation and must not be used for real grid dispatch
decisions without full engineering validation.
