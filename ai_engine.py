"""
ZESCO DLR Digital Twin - AI / Analytics Layer
==============================================
Adds lightweight ML-style analytics on top of the IEEE 738 engine, using
only the Python standard library so the service stays light on Render:

  - Trend forecasting    : projects load & weather forward, then runs the
                           thermal model to predict temperature & rating.
  - Anomaly detection    : z-score outlier detection plus physics
                           model-vs-measured mismatch checks.
  - Overload risk        : probability-style risk score over the horizon.
  - AI insights          : natural-language situational-awareness text.
  - Assistant            : answers natural-language queries. If the
                           OPENAI_API_KEY env var is set, it upgrades to a
                           real LLM; otherwise it falls back to a built-in
                           rule-based reasoning engine.

The simulated site location (ZESCO line, Copperbelt, Zambia):
    lat -12.693845, lon 28.184119
"""

import json
import math
import os
import statistics
import urllib.request

SITE_LAT = -12.693845
SITE_LON = 28.184119
SITE_NAME = "ZESCO Copperbelt Line Node"

# Plausible physical ranges for clamping forecasts
LIMITS = {
    "ambient_temp": (0.0, 50.0),
    "wind_speed": (0.0, 30.0),
    "current_load": (0.0, 9.0),
}


def _lsq(ys):
    """Least-squares slope & intercept for a time series (uniform spacing)."""
    n = len(ys)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    intercept = my - slope * mx
    return slope, intercept


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _winsorize(vals):
    """Trim outliers to within 2.5 standard deviations so a single sensor
    spike does not dominate the trend forecast."""
    vals = list(vals)
    if len(vals) < 3:
        return vals
    mu = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    if sd < 1e-9:
        return vals
    lo, hi = mu - 2.5 * sd, mu + 2.5 * sd
    return [min(max(v, lo), hi) for v in vals]


# ----------------------------------------------------------------------
# Trend forecasting
# ----------------------------------------------------------------------
def forecast(records, engine, horizon_min=60, step_min=5, lookback=30):
    """Project ambient, wind and load forward and compute the resulting
    conductor temperature and dynamic rating for each step ahead.

    Uses a least-squares linear trend blended with mean reversion so the
    projection stays physically plausible.
    """
    rows = (records or [])[-lookback:]
    if len(rows) < 5:
        return None

    def series(key):
        vals = [r.get(key) for r in rows if r.get(key) is not None]
        return vals

    def project(key):
        vals = _winsorize(series(key))
        mean = statistics.mean(vals)
        recent_hi = max(vals) if vals else LIMITS[key][1]
        slope, intercept = _lsq(vals)
        last_idx = len(vals) - 1
        out = []
        for k in range(1, int(horizon_min / step_min) + 1):
            raw = intercept + slope * (last_idx + k * step_min)
            blended = 0.4 * raw + 0.6 * mean
            hi_cap = min(LIMITS[key][1], recent_hi * 1.25)
            out.append(_clamp(blended, LIMITS[key][0], hi_cap))
        return out

    ambient = project("ambient_temp")
    wind = project("wind_speed")
    current = project("current_load")

    temp = []
    rating = []
    for i in range(len(current)):
        temp.append(engine.predict_temperature(current[i], ambient[i], wind[i]))
        rating.append(engine.calculate_dynamic_rating(ambient[i], wind[i]))

    labels = [f"{step_min * (i + 1)} min" for i in range(len(current))]
    return {
        "labels": labels,
        "ambient_temp": [round(v, 1) for v in ambient],
        "wind_speed": [round(v, 1) for v in wind],
        "current_load": [round(v, 2) for v in current],
        "conductor_temp": temp,
        "dynamic_rating": rating,
        "static_rating": engine.static_rating,
        "max_temp": engine.max_temp,
    }


# ----------------------------------------------------------------------
# Anomaly detection
# ----------------------------------------------------------------------
def detect_anomalies(records, engine, lookback=40):
    """Flag unusual readings (z-score outliers) and physics mismatches
    between the measured conductor temperature and the IEEE 738 model."""
    rows = (records or [])[-lookback:]
    if len(rows) < 5:
        return []

    anomalies = []
    checks = [
        ("current_load", "Load"),
        ("conductor_temp", "Conductor temp"),
        ("ambient_temp", "Ambient temp"),
        ("wind_speed", "Wind speed"),
    ]
    for field, label in checks:
        vals = [r.get(field) for r in rows if r.get(field) is not None]
        if len(vals) < 5:
            continue
        mu = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        if sd < 1e-9:
            continue
        for r in rows[-3:]:
            v = r.get(field)
            if v is None:
                continue
            if abs(v - mu) > 3.0 * sd:
                anomalies.append(
                    {
                        "type": field,
                        "level": "high",
                        "text": (
                            f"Abnormal {label}: {v:.2f} is far from the recent "
                            f"average of {mu:.2f} (z={abs(v - mu) / sd:.1f})."
                        ),
                    }
                )

    for r in rows[-3:]:
        cond = r.get("conductor_temp")
        if cond is None or cond <= 0:
            continue
        model = engine.predict_temperature(
            r.get("current_load", 0), r.get("ambient_temp", 25), r.get("wind_speed", 1)
        )
        if abs(model - cond) > 12.0:
            anomalies.append(
                {
                    "type": "sensor_mismatch",
                    "level": "medium",
                    "text": (
                        f"Sensor/model mismatch: measured {cond:.1f} C vs model "
                        f"{model:.1f} C. Check the DS18B20 mount."
                    ),
                }
            )

    return anomalies


# ----------------------------------------------------------------------
# Overload risk scoring
# ----------------------------------------------------------------------
def assess_risk(records, engine, horizon_min=30):
    """Probability-style risk that the line approaches/exceeds its dynamic
    limit. Driven mainly by current loading; the trend forecast adds a
    boost when loading is projected to tighten."""
    empty = {"score": 0, "band": "LOW", "load_ratio": 0.0, "temp_margin": None}
    if not records:
        return empty

    latest = records[-1]
    r0 = 0.0
    if latest.get("dynamic_rating", 0) > 0:
        r0 = latest["current_load"] / latest["dynamic_rating"]

    fc = forecast(records, engine, horizon_min)
    r_fc = r0
    temp_margin = None
    overloaded = False
    if fc:
        ratios = [fc["current_load"][i] / fc["dynamic_rating"][i] for i in range(len(fc["current_load"]))]
        r_fc = max(ratios)
        overloaded = any(r >= 1.0 for r in ratios)
        temp_margin = engine.max_temp - max(fc["conductor_temp"])

    score = round(min(100.0, 100.0 * max(r0, 0.8 * r_fc)))
    if overloaded:
        score = max(score, 85)
    if temp_margin is not None and temp_margin < 10:
        score = max(score, 70)

    if score >= 85:
        band = "HIGH"
    elif score >= 65:
        band = "MEDIUM"
    else:
        band = "LOW"

    return {
        "score": score,
        "band": band,
        "load_ratio": round(max(r0, r_fc), 2),
        "temp_margin": round(temp_margin, 1) if temp_margin is not None else None,
        "horizon_min": horizon_min,
    }


# ----------------------------------------------------------------------
# Natural-language insights (rule-based NLG)
# ----------------------------------------------------------------------
def _latest(records):
    return (records or [])[-1] or {}


def generate_insights(records, engine):
    """Generate a ranked list of situational-awareness insights."""
    insights = []
    if not records:
        return insights
    latest = _latest(records)
    status = latest.get("status")

    if status == "CRITICAL":
        insights.append(
            {
                "level": "critical",
                "text": (
                    f"Line is CRITICALLY overloaded at {latest['current_load']:.2f} A "
                    f"vs a dynamic limit of {latest['dynamic_rating']:.2f} A. Thermal "
                    f"sag risk is elevated."
                ),
            }
        )
    elif status == "WARNING":
        insights.append(
            {
                "level": "info",
                "text": (
                    f"Operating above the static limit ({latest['static_rating']:.2f} A) "
                    f"but wind cooling ({latest['wind_speed']:.1f} m/s) safely unlocks "
                    f"{latest['capacity_gain_pct']:.0f}% extra capacity."
                ),
            }
        )
    else:
        insights.append(
            {
                "level": "ok",
                "text": (
                    f"Line is operating within limits. Dynamic headroom is "
                    f"{latest['dynamic_rating'] - latest['current_load']:.2f} A."
                ),
            }
        )

    rows = (records or [])[-12:]
    loads = [r.get("current_load") for r in rows if r.get("current_load") is not None]
    if len(loads) >= 6:
        slope, _ = _lsq(loads)
        per_hour = slope * 60
        if per_hour > 0.15:
            insights.append(
                {
                    "level": "warning",
                    "text": (
                        f"Load is trending UP by ~{per_hour:.2f} A/hour. Anticipate "
                        f"rising conductor temperature."
                    ),
                }
            )
        elif per_hour < -0.15:
            insights.append(
                {
                    "level": "ok",
                    "text": f"Load is trending DOWN by ~{-per_hour:.2f} A/hour.",
                }
            )

    temp_margin = engine.max_temp - latest.get("conductor_temp", 0)
    if temp_margin < 10:
        insights.append(
            {
                "level": "warning",
                "text": (
                    f"Conductor temperature is only {temp_margin:.1f} C below the "
                    f"{engine.max_temp:.0f} C limit."
                ),
            }
        )

    if latest.get("wind_speed", 0) >= 4:
        insights.append(
            {
                "level": "ok",
                "text": (
                    f"Strong wind ({latest['wind_speed']:.1f} m/s) is enhancing "
                    f"convective cooling - dynamic rating is favourable."
                ),
            }
        )

    return insights[:5]


# ----------------------------------------------------------------------
# Assistant (rule-based reasoning, optionally LLM-upgraded)
# ----------------------------------------------------------------------
def build_context(records, engine):
    latest = _latest(records)
    risk = assess_risk(records, engine)
    anomalies = detect_anomalies(records, engine)
    fc = forecast(records, engine, horizon_min=30)
    return {
        "site": SITE_NAME,
        "location": f"{SITE_LAT:.5f}, {SITE_LON:.5f}",
        "latest": latest,
        "risk": risk,
        "anomalies": anomalies,
        "forecast30": fc,
    }


def _fmt_latest(ctx):
    l = ctx["latest"]
    if not l:
        return "No telemetry yet."
    return (
        f"Load {l['current_load']:.2f} A | dynamic limit {l['dynamic_rating']:.2f} A | "
        f"conductor temp {l['conductor_temp']:.1f} C | ambient {l['ambient_temp']:.1f} C | "
        f"wind {l['wind_speed']:.1f} m/s | sag {l['sag_m']:.2f} m | status {l['status']}."
    )


def _answer(query, ctx):
    q = query.lower()

    def has(*words):
        return any(w in q for w in words)

    if has("overload", "risk", "critical", "danger", "safe"):
        r = ctx["risk"]
        l = ctx["latest"]
        if not l:
            return "No data yet to assess risk."
        if l["status"] == "CRITICAL":
            return (
                f"{_fmt_latest(ctx)} The line is CRITICALLY overloaded. Forecast risk is "
                f"{r['band']} ({r['score']}/100). Recommendation: reduce load or increase "
                f"dispatch coordination immediately."
            )
        if r["band"] != "LOW":
            return (
                f"Overload risk is {r['band']} ({r['score']}/100) over the next "
                f"{r['horizon_min']} min. The line is within limits now but headroom is "
                f"shrinking. Monitor load trends."
            )
        return (
            f"Overload risk is LOW ({r['score']}/100). Current status: {l['status']}. "
            f"Dynamic headroom is {l['dynamic_rating'] - l['current_load']:.2f} A."
        )

    if has("capacity", "rating", "dlr", "gain", "dynamic", "ampacity"):
        l = ctx["latest"]
        if not l:
            return "No data yet to compute capacity."
        return (
            f"Current dynamic rating is {l['dynamic_rating']:.2f} A vs a static rating of "
            f"{l['static_rating']:.2f} A - a {l['capacity_gain_pct']:.0f}% capacity gain "
            f"unlocked by wind cooling ({l['wind_speed']:.1f} m/s at {l['ambient_temp']:.1f} C). "
            f"Loading is {l['current_load']:.2f} A."
        )

    if has("sag", "clearance", "drop"):
        l = ctx["latest"]
        if not l:
            return "No data yet to estimate sag."
        return (
            f"At {l['conductor_temp']:.1f} C the estimated mid-span sag is "
            f"{l['sag_m']:.2f} m, leaving ~{l['clearance_m']:.2f} m ground clearance. "
            f"The minimum recommended clearance is around 5.5 m."
        )

    if has("anomal", "sensor", "fault", "error", "weird"):
        a = ctx["anomalies"]
        if not a:
            return "No anomalies detected in the recent telemetry. All sensors look healthy."
        return (
            f"I detected {len(a)} anomaly/ies: " + "; ".join(x["text"] for x in a[:3]) +
            " Recommend inspecting the affected sensor(s)."
        )

    if has("forecast", "predict", "next", "future", "hour", "ahead", "look"):
        fc = ctx["forecast30"]
        if not fc:
            return "Not enough history yet for a forecast (need at least 5 readings)."
        return (
            f"Over the next 30 min I expect load around {fc['current_load'][-1]:.2f} A, "
            f"conductor temp about {fc['conductor_temp'][-1]:.1f} C, and a dynamic rating "
            f"of {fc['dynamic_rating'][-1]:.2f} A."
        )

    if has("temp", "heat", "hot", "warm"):
        l = ctx["latest"]
        if not l:
            return "No temperature data yet."
        margin = 75.0 - l["conductor_temp"]
        return (
            f"Conductor temperature is {l['conductor_temp']:.1f} C (margin "
            f"{margin:.1f} C to the 75 C limit). Ambient is {l['ambient_temp']:.1f} C."
        )

    if has("recommend", "should", "action", "do", "advice", "tip"):
        l = ctx["latest"]
        if not l:
            return "No data yet for recommendations."
        r = ctx["risk"]
        if l["status"] == "CRITICAL":
            return "Reduce load now, dispatch a line inspection crew, and review sag/clearance readings."
        if r["band"] != "LOW":
            return "Increase monitoring cadence, watch for load spikes, and validate wind measurements before relying on dynamic capacity."
        return "Line is healthy. Consider scheduling maintenance or capturing a baseline data batch for the digital twin."

    if has("hello", "hi ", "hey", "help", "who", "what can"):
        return (
            f"Hi! I am the DLR Digital Twin assistant for {ctx['site']} "
            f"({ctx['location']}). Ask me about status, overload risk, dynamic capacity, "
            f"sag, temperature, anomalies, forecasts, or recommendations."
        )

    return (
        f"Here is the current system state: {_fmt_latest(ctx)} "
        f"Overload risk: {ctx['risk']['band']} ({ctx['risk']['score']}/100). "
        f"You can ask about capacity, sag, anomalies, temperature, forecast, or what to do."
    )


def _llm_answer(query, ctx):
    """Optional LLM upgrade. Requires OPENAI_API_KEY to be set."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the AI assistant of the ZESCO Dynamic Line Rating digital "
                    "twin. Be concise, technical and actionable. Use the supplied context. "
                    f"Context: {json.dumps(ctx, default=str)[:4000]}"
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": 200,
        "temperature": 0.4,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def assistant(query, records, engine):
    ctx = build_context(records, engine)
    if os.environ.get("OPENAI_API_KEY"):
        try:
            llm = _llm_answer(query, ctx)
            if llm:
                return llm
        except Exception:
            pass
    return _answer(query, ctx)
