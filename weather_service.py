"""
ZESCO DLR Digital Twin - Open-Meteo Weather Forecast Client
==========================================================
Fetches hourly weather forecasts from the free Open-Meteo API
(no API key required) and caches results to limit API calls.

Provides ambient temperature, wind speed, humidity and solar
radiation for the site location. Used by the 24h DLR forecast.
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SITE_LAT = -12.693845
SITE_LON = 28.184119

API_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 900  # 15 minutes

_cache = None
_cache_time = 0


class WeatherFetchError(Exception):
    """Raised when the Open-Meteo API cannot be reached or returns bad data."""


def _build_url() -> str:
    params = {
        "latitude": str(SITE_LAT),
        "longitude": str(SITE_LON),
        "hourly": "temperature_2m,windspeed_10m,relative_humidity_2m,shortwave_radiation",
        "timezone": "auto",
        "forecast_days": "1",
    }
    return API_URL + "?" + urllib.parse.urlencode(params)


def _parse_hourly(payload: dict) -> list:
    """Extract the next 24 hourly entries from an Open-Meteo response."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    winds = hourly.get("windspeed_10m") or []
    hums = hourly.get("relative_humidity_2m") or []
    rads = hourly.get("shortwave_radiation") or []

    if not times:
        raise WeatherFetchError("No hourly forecast data in API response")

    hours = []
    for t, temp, wind, hum, rad in zip(times, temps, winds, hums, rads):
        hours.append(
            {
                "hour": t[11:16],  # "HH:MM"
                "ambient": round(float(temp), 1),
                "wind": round(float(wind), 1),
                "humidity": round(float(hum), 1),
                "solar_radiation": round(float(rad), 1),  # W/m^2 GHI
            }
        )
        if len(hours) >= 24:
            break
    return hours


def fetch_forecast(force_refresh: bool = False) -> list:
    """Return a cached 24h weather forecast, refreshing if stale.

    Returns a list of dicts:
        [{ "hour", "ambient", "wind", "humidity", "solar_radiation" }, ...]
    Raises WeatherFetchError on any failure.
    """
    global _cache, _cache_time

    now = time.time()
    if not force_refresh and _cache is not None and (now - _cache_time) < CACHE_TTL_SECONDS:
        return _cache

    url = _build_url()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ZESCO-DLR-DigitalTwin/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        hours = _parse_hourly(payload)
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise WeatherFetchError(f"Open-Meteo request failed: {exc}") from exc

    if not hours:
        raise WeatherFetchError("Open-Meteo returned an empty forecast")

    _cache = hours
    _cache_time = now
    return hours
