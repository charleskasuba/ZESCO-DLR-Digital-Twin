"""
ZESCO DLR Digital Twin - Flask Backend & REST API
==================================================
Serves the operator dashboard and exposes a REST API for:

    - ESP32 telemetry ingestion          POST /api/telemetry
    - Live / historical telemetry        GET  /api/telemetry/...
    - Dynamic Line Rating engine         GET  /api/dlr/...
    - Thermal sag & clearance            GET  /api/dlr/sag
    - 24h rating forecast                GET  /api/forecast
    - CSV export of history              GET  /api/telemetry/export
    - Interactive API docs               /docs

Run locally:  python app.py
Run on Render: gunicorn app:app
"""

import csv
import io
import math
import os
import random
from datetime import datetime, timedelta, timezone

from apiflask import APIFlask, Schema, fields

from flask import Response, render_template, request

import database as db
import ai_engine as ai
import weather_service as wx
from dlr_engine import WireDigitalTwin

app = APIFlask(
    __name__,
    title="ZESCO DLR Digital Twin API",
    version="1.0.0",
    docs_ui="swagger-ui",
)
app.config["SPEC_FORMAT"] = "json"

# ----------------------------------------------------------------------
# Single shared twin instance (IEEE 738 engine)
#
# NOTE: R_ref=75 ohm is tuned for the lab-scale demo rig (thin heating
# element + 5 A ACS712). Real HV conductors use milliohm resistances and
# ratings in the hundreds of amps.
# ----------------------------------------------------------------------
twin = WireDigitalTwin(
    R_ref=75.0,
    alpha=0.004,
    max_temp=75.0,
    emissivity=0.5,
    static_rating=3.0,
    span_length=150.0,
    clearance_ref=8.0,
)


# ----------------------------------------------------------------------
# Schemas (used for API validation + auto OpenAPI docs)
# ----------------------------------------------------------------------
class TelemetryIn(Schema):
    conductor_temp = fields.Float(
        required=True, metadata={"description": "Conductor temp (deg C)"}
    )
    ambient_temp = fields.Float(
        required=True, metadata={"description": "Ambient temp (deg C)"}
    )
    humidity = fields.Float(
        load_default=50.0, metadata={"description": "Relative humidity (%)"}
    )
    wind_speed = fields.Float(
        required=True, metadata={"description": "Wind speed (m/s)"}
    )
    current_load = fields.Float(
        required=True, metadata={"description": "Line current (A)"}
    )


class TelemetryOut(Schema):
    id = fields.Integer()
    timestamp = fields.String()
    conductor_temp = fields.Float()
    ambient_temp = fields.Float()
    humidity = fields.Float()
    wind_speed = fields.Float()
    current_load = fields.Float()
    static_rating = fields.Float()
    dynamic_rating = fields.Float()
    capacity_gain_pct = fields.Float()
    model_temp = fields.Float()
    sag_m = fields.Float()
    clearance_m = fields.Float()
    status = fields.String()


class HealthOut(Schema):
    status = fields.String()
    time = fields.String()
    readings = fields.Integer()
    twin = fields.Dict()


class EventOut(Schema):
    id = fields.Integer()
    timestamp = fields.String()
    level = fields.String()
    message = fields.String()


# ----------------------------------------------------------------------
# Startup: init DB and seed demo history so the dashboard is never empty
# ----------------------------------------------------------------------
def _seed_demo_data():
    db.init_db()
    if db.count_telemetry() > 0:
        return

    now = datetime.now(timezone.utc)
    seed_records = []
    for i in range(90):
        ts = (now - timedelta(minutes=90 - i)).isoformat(timespec="seconds")
        ambient = 24.0 + 4.0 * math.sin(i / 8.0) + random.uniform(-1.0, 1.0)
        wind = max(0.2, 2.2 + 1.4 * math.sin(i / 5.0) + random.uniform(-0.6, 0.6))
        current = max(0.5, 1.9 + 0.45 * math.sin(i / 6.0) + random.uniform(-0.2, 0.2))
        rec = twin.evaluate(current, ambient, wind)
        rec.update(
            {
                "timestamp": ts,
                "humidity": round(55.0 + random.uniform(-8, 8), 1),
                "conductor_temp": rec["model_temp"],
            }
        )
        seed_records.append(rec)

    for rec in seed_records:
        db.insert_telemetry(rec)
    db.insert_event("INFO", "System initialised - demo telemetry seeded")


_seed_demo_data()


# ----------------------------------------------------------------------
# Page routes
# ----------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
@app.output(HealthOut)
def health():
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "readings": db.count_telemetry(),
        "twin": {
            "static_rating_a": twin.static_rating,
            "max_temp_c": twin.max_temp,
            "span_m": twin.span_length,
            "standard": "IEEE Std 738",
        },
    }


# ----------------------------------------------------------------------
# Telemetry ingestion
# ----------------------------------------------------------------------
@app.post("/api/telemetry")
@app.input(TelemetryIn)
@app.output(TelemetryOut, status_code=201)
def ingest_telemetry(json_data: dict):
    """Ingest a sensor reading from the ESP32 or simulator.

    Computes the DLR snapshot and persists it to the history database,
    raising alert events whenever the line crosses a safety threshold.
    """
    rec = twin.evaluate(
        current=json_data["current_load"],
        ambient=json_data["ambient_temp"],
        wind_speed=json_data["wind_speed"],
        measured_temp=json_data["conductor_temp"],
    )
    rec["timestamp"] = db.message_timestamp()
    rec["humidity"] = json_data.get("humidity")
    rec["id"] = db.insert_telemetry(rec)

    _log_status_event(rec)
    return rec


def _log_status_event(rec: dict):
    status = rec["status"]
    if status == "OK":
        return
    last_level = db.last_event_level()
    if last_level == status:
        return
    if status == "CRITICAL":
        msg = (
            f"CRITICAL OVERLOAD: {rec['current_load']} A exceeds dynamic limit "
            f"{rec['dynamic_rating']} A. Sagging {rec['sag_m']} m, "
            f"clearance {rec['clearance_m']} m. Reduce load or dispatch crew."
        )
    else:
        msg = (
            f"WARNING: {rec['current_load']} A above static limit "
            f"{rec['static_rating']} A but within dynamic limit "
            f"{rec['dynamic_rating']} A - wind cooling enabled."
        )
    db.insert_event(status, msg)


@app.post("/api/demo/telemetry")
@app.input(TelemetryIn)
@app.output(TelemetryOut, status_code=201)
def demo_telemetry(json_data: dict):
    """Inject a synthetic reading (used by the dashboard simulator)."""
    rec = twin.evaluate(
        current=json_data["current_load"],
        ambient=json_data["ambient_temp"],
        wind_speed=json_data["wind_speed"],
        measured_temp=json_data["conductor_temp"],
    )
    rec["timestamp"] = db.message_timestamp()
    rec["humidity"] = json_data.get("humidity")
    rec["id"] = db.insert_telemetry(rec)
    _log_status_event(rec)
    return rec


# ----------------------------------------------------------------------
# Telemetry reads
# ----------------------------------------------------------------------
@app.get("/api/telemetry/latest")
@app.output(TelemetryOut)
def latest_telemetry():
    """Latest processed sensor reading (or the last seeded point)."""
    row = db.latest_telemetry()
    if row is None:
        return {"status": "OK"}
    return row


@app.get("/api/telemetry/history")
@app.output(TelemetryOut(many=True))
def telemetry_history():
    """Rolling telemetry history, newest first, up to `limit` rows."""
    limit = min(int(request.args.get("limit", 60)), 500)
    rows = db.history(limit)
    return list(reversed(rows))


@app.get("/api/telemetry/events")
@app.output(EventOut(many=True))
def telemetry_events():
    """Alert / status-transition event log."""
    return db.events(int(request.args.get("limit", 20)))


@app.get("/api/telemetry/export")
def telemetry_export():
    """Download the full telemetry history as CSV."""
    rows = db.history(1000)
    buf = io.StringIO()
    fieldnames = [
        "timestamp", "conductor_temp", "ambient_temp", "humidity",
        "wind_speed", "current_load", "static_rating", "dynamic_rating",
        "capacity_gain_pct", "model_temp", "sag_m", "clearance_m", "status",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows({k: row.get(k) for k in fieldnames} for row in rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=dlr_telemetry.csv"},
    )


# ----------------------------------------------------------------------
# DLR engine endpoints
# ----------------------------------------------------------------------
@app.get("/api/dlr/rating")
@app.output(TelemetryOut)
def dlr_rating():
    """Dynamic ampacity under given weather conditions."""
    ambient = float(request.args.get("ambient", 25.0))
    wind = float(request.args.get("wind", 2.0))
    current = float(request.args.get("current", 2.0))
    rec = twin.evaluate(current, ambient, wind)
    return rec


@app.get("/api/dlr/calculate")
@app.output(TelemetryOut)
def dlr_calculate():
    """Forward twin: predicted conductor temperature for a load + weather."""
    ambient = float(request.args.get("ambient", 25.0))
    wind = float(request.args.get("wind", 2.0))
    current = float(request.args.get("current", 2.5))
    temp = twin.predict_temperature(current, ambient, wind)
    rec = twin.evaluate(current, ambient, wind, measured_temp=temp)
    return rec


@app.get("/api/dlr/sag")
@app.output(TelemetryOut)
def dlr_sag():
    """Thermal sag & ground clearance at a given conductor temperature."""
    temp = float(request.args.get("temp", 40.0))
    ambient = float(request.args.get("ambient", 25.0))
    wind = float(request.args.get("wind", 2.0))
    rec = twin.evaluate(2.0, ambient, wind, measured_temp=temp)
    return rec


# ----------------------------------------------------------------------
# 24h rating forecast
# ----------------------------------------------------------------------
@app.get("/api/forecast")
def rating_forecast():
    """24-hour DLR outlook for planning / operator awareness.

    Uses a real weather forecast from Open-Meteo when available, and
    falls back to a synthetic diurnal profile if the API is unreachable.
    """
    now = datetime.now(timezone.utc)
    hours = []
    ambient_curve = []
    wind_curve = []
    humidity_curve = []
    solar_curve = []
    rating_curve = []
    source = "synthetic"
    data_items = None

    try:
        data_items = wx.fetch_forecast()
        source = "open-meteo"
    except wx.WeatherFetchError:
        pass

    if data_items:
        for i, item in enumerate(data_items):
            hours.append(item["hour"])
            ambient = item["ambient"]
            wind = item["wind"]
            humidity = item["humidity"]
            solar = item["solar_radiation"]
            rating = twin.calculate_dynamic_rating(ambient, wind)
            ambient_curve.append(round(ambient, 1))
            wind_curve.append(round(wind, 1))
            humidity_curve.append(round(humidity, 1))
            solar_curve.append(round(solar, 1))
            rating_curve.append(rating)
    else:
        # Fallback: synthetic diurnal profile
        for i in range(24):
            hours.append((now + timedelta(hours=i)).strftime("%H:%M"))
            hour_of_day = (now + timedelta(hours=i)).hour
            ambient = 20.0 + 9.0 * math.sin(math.pi * (hour_of_day - 6.0) / 12.0)
            ambient = max(14.0, min(38.0, ambient + random.uniform(-1.5, 1.5)))
            wind = 2.0 + 1.6 * math.sin(math.pi * (hour_of_day - 9.0) / 10.0)
            wind = max(0.5, wind + random.uniform(-0.7, 0.7))
            rating = twin.calculate_dynamic_rating(ambient, wind)
            ambient_curve.append(round(ambient, 1))
            wind_curve.append(round(wind, 1))
            humidity_curve.append(round(55.0, 1))
            solar_curve.append(0.0)
            rating_curve.append(rating)

    return {
        "hours": hours,
        "ambient": ambient_curve,
        "wind": wind_curve,
        "humidity": humidity_curve,
        "solar_radiation": solar_curve,
        "dynamic_rating": rating_curve,
        "static_rating": twin.static_rating,
        "max_temp": twin.max_temp,
        "source": source,
    }


# ----------------------------------------------------------------------
# AI / analytics endpoints
# ----------------------------------------------------------------------
def _recent_records(limit=60):
    return db.history(limit)


@app.get("/api/ai/insights")
def ai_insights():
    """Natural-language situational-awareness insights from the twin."""
    return {"insights": ai.generate_insights(_recent_records(), twin)}


@app.get("/api/ai/forecast")
def ai_forecast():
    """AI trend forecast of load, weather, temperature and dynamic rating."""
    horizon = int(request.args.get("horizon", 60))
    step = int(request.args.get("step", 5))
    return ai.forecast(_recent_records(), twin, horizon_min=horizon, step_min=step) or {
        "message": "Not enough history yet"
    }


@app.get("/api/ai/anomalies")
def ai_anomalies():
    """Detected sensor anomalies / physics mismatches."""
    return {"anomalies": ai.detect_anomalies(_recent_records(), twin)}


@app.get("/api/ai/risk")
def ai_risk():
    """Overload risk score & band over the forecast horizon."""
    return ai.assess_risk(_recent_records(), twin)


@app.get("/api/site")
def site_info():
    """Simulated line site / asset metadata for the map."""
    return {
        "name": ai.SITE_NAME,
        "lat": ai.SITE_LAT,
        "lon": ai.SITE_LON,
        "zoom": 15.89,
        "span_m": twin.span_length,
        "openinframap_url": "https://openinframap.org/#15.89/-12.693845/28.184119",
        "route": [
            {"lat": -12.7035, "lon": 28.1745},
            {"lat": -12.6988, "lon": 28.1790},
            {"lat": ai.SITE_LAT, "lon": ai.SITE_LON},
            {"lat": -12.6890, "lon": 28.1890},
            {"lat": -12.6840, "lon": 28.1940},
        ],
    }


class AssistantIn(Schema):
    query = fields.String(required=True, metadata={"description": "Natural-language question"})


class AssistantOut(Schema):
    answer = fields.String()
    mode = fields.String()


@app.post("/api/ai/assistant")
@app.input(AssistantIn)
@app.output(AssistantOut)
def ai_assistant(json_data: dict):
    """Ask the AI assistant a natural-language question."""
    answer = ai.assistant(json_data["query"], _recent_records(), twin)
    mode = "llm" if os.environ.get("OPENAI_API_KEY") else "builtin"
    return {"answer": answer, "mode": mode}


@app.get("/api")
def api_index():
    return {
        "name": "ZESCO DLR Digital Twin API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/health",
            "ingest_telemetry": "POST /api/telemetry",
            "inject_demo": "POST /api/demo/telemetry",
            "latest": "/api/telemetry/latest",
            "history": "/api/telemetry/history",
            "events": "/api/telemetry/events",
            "csv_export": "/api/telemetry/export",
            "dlr_rating": "/api/dlr/rating",
            "dlr_calculate": "/api/dlr/calculate",
            "dlr_sag": "/api/dlr/sag",
            "forecast": "/api/forecast",
            "ai_insights": "/api/ai/insights",
            "ai_forecast": "/api/ai/forecast",
            "ai_anomalies": "/api/ai/anomalies",
            "ai_risk": "/api/ai/risk",
            "ai_assistant": "POST /api/ai/assistant",
            "site": "/api/site",
        },
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
