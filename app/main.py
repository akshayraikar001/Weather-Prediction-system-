import json
from datetime import date, datetime
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_PATH = BASE_DIR / "models" / "rain_tomorrow_model.pkl"
DATA_PATH = BASE_DIR / "archive" / "india_historical_daily_weather.csv"
STATIC_DIR = BASE_DIR / "frontend"
DEFAULT_CITY = "Pune"
LIVE_CACHE_TTL_SECONDS = 600

model_bundle = joblib.load(MODEL_PATH)
model = model_bundle["model"]
supported_cities = model_bundle["cities"]
city_reference = (
    pd.read_csv(DATA_PATH)
    .sort_values(["city", "date"])
    .groupby("city", as_index=False)
    .first()[["city", "state", "latitude", "longitude"]]
)
city_reference = city_reference[city_reference["city"].isin(supported_cities)].copy()
city_lookup = {
    row["city"]: {
        "state": row["state"],
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
    }
    for _, row in city_reference.iterrows()
}

app = FastAPI(title="Weather Prediction System", version="1.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
snapshot_cache: dict[str, tuple[float, dict]] = {}


class PredictionRequest(BaseModel):
    city: str = Field(..., examples=["Pune"])
    temperature_celsius: float
    humidity: float = Field(..., ge=0, le=100)
    pressure_mb: float
    wind_speed_kph: float = Field(..., ge=0)
    cloud_cover: float = Field(..., ge=0, le=100)
    rain_today: int = Field(..., ge=0, le=1)
    observation_date: date | None = None


class CityRequest(BaseModel):
    city: str = Field(DEFAULT_CITY, examples=["Pune"])


class PredictionResponse(BaseModel):
    rain_tomorrow: str
    confidence_score: float
    rain_probability: float
    observation_date: str


def ensure_supported_city(city: str) -> dict:
    if city not in city_lookup:
        raise HTTPException(status_code=404, detail=f"Unsupported city: {city}")
    return city_lookup[city]


def call_open_meteo(params: dict) -> dict | list:
    url = "https://api.open-meteo.com/v1/forecast?" + urlencode(params)
    try:
        with urlopen(url, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Live weather provider error: {exc}",
        ) from exc


def get_cached_snapshot(city: str) -> dict | None:
    cached = snapshot_cache.get(city)
    if not cached:
        return None

    cached_at, payload = cached
    if monotonic() - cached_at > LIVE_CACHE_TTL_SECONDS:
        snapshot_cache.pop(city, None)
        return None

    return payload


def set_cached_snapshot(city: str, payload: dict) -> None:
    snapshot_cache[city] = (monotonic(), payload)


def build_heat_points(latitude: float, longitude: float) -> list[dict]:
    offsets = [-0.18, 0.0, 0.18]
    points = [
        (round(latitude + lat_offset, 4), round(longitude + lon_offset, 4))
        for lat_offset in offsets
        for lon_offset in offsets
    ]
    try:
        payload = call_open_meteo(
            {
                "latitude": ",".join(str(point[0]) for point in points),
                "longitude": ",".join(str(point[1]) for point in points),
                "current": "temperature_2m",
                "timezone": "Asia/Kolkata",
            }
        )
    except HTTPException:
        return []

    responses = payload if isinstance(payload, list) else [payload]

    return [
        {
            "latitude": point[0],
            "longitude": point[1],
            "temperature_celsius": float(item["current"]["temperature_2m"]),
        }
        for point, item in zip(points, responses)
    ]


def fetch_live_snapshot(city: str) -> dict:
    cached_snapshot = get_cached_snapshot(city)
    if cached_snapshot:
        return cached_snapshot

    reference = ensure_supported_city(city)
    try:
        live_payload = call_open_meteo(
            {
                "latitude": reference["latitude"],
                "longitude": reference["longitude"],
                "current": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "pressure_msl",
                        "wind_speed_10m",
                        "cloud_cover",
                        "rain",
                        "weather_code",
                    ]
                ),
                "daily": ",".join(
                    [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                        "rain_sum",
                    ]
                ),
                "timezone": "Asia/Kolkata",
                "forecast_days": 3,
            }
        )
    except HTTPException:
        if cached_snapshot:
            return cached_snapshot
        raise

    current = live_payload["current"]
    daily = live_payload.get("daily", {})
    observation_date = current["time"].split("T")[0]
    rain_today = 1 if float(current.get("rain", 0) or 0) > 0 else 0

    snapshot = {
        "city": city,
        "state": reference["state"],
        "latitude": reference["latitude"],
        "longitude": reference["longitude"],
        "observation_date": observation_date,
        "current": {
            "temperature_celsius": float(current["temperature_2m"]),
            "humidity": float(current["relative_humidity_2m"]),
            "pressure_mb": float(current["pressure_msl"]),
            "wind_speed_kph": float(current["wind_speed_10m"]),
            "cloud_cover": float(current["cloud_cover"]),
            "rain_mm": float(current.get("rain", 0) or 0),
            "rain_today": rain_today,
            "weather_code": int(current["weather_code"]),
        },
        "today_summary": {
            "temperature_max_celsius": float(daily.get("temperature_2m_max", [current["temperature_2m"]])[0]),
            "temperature_min_celsius": float(daily.get("temperature_2m_min", [current["temperature_2m"]])[0]),
            "precipitation_probability_max": float(daily.get("precipitation_probability_max", [0])[0] or 0),
            "rain_sum_mm": float(daily.get("rain_sum", [0])[0] or 0),
        },
        "daily_forecast": [
            {
                "date": daily["time"][index],
                "weather_code": int(daily.get("weather_code", [0])[index]),
                "temperature_max_celsius": float(daily.get("temperature_2m_max", [current["temperature_2m"]])[index]),
                "temperature_min_celsius": float(daily.get("temperature_2m_min", [current["temperature_2m"]])[index]),
                "precipitation_probability_max": float(daily.get("precipitation_probability_max", [0])[index] or 0),
                "rain_sum_mm": float(daily.get("rain_sum", [0])[index] or 0),
            }
            for index in range(min(3, len(daily.get("time", []))))
        ],
        "heat_points": build_heat_points(reference["latitude"], reference["longitude"]),
    }

    if not snapshot["heat_points"]:
        snapshot["heat_points"] = [
            {
                "latitude": reference["latitude"],
                "longitude": reference["longitude"],
                "temperature_celsius": snapshot["current"]["temperature_celsius"],
            }
        ]

    set_cached_snapshot(city, snapshot)
    return snapshot


def predict_from_features(features: dict, observed_on: date) -> PredictionResponse:
    model_input = pd.DataFrame(
        [
            {
                "city": features["city"],
                "temperature_celsius": features["temperature_celsius"],
                "humidity": features["humidity"],
                "pressure_mb": features["pressure_mb"],
                "wind_speed_kph": features["wind_speed_kph"],
                "cloud_cover": features["cloud_cover"],
                "rain_today": features["rain_today"],
                "month": observed_on.month,
            }
        ]
    )
    rain_probability = float(model.predict_proba(model_input)[0][1])
    will_rain = rain_probability >= 0.5

    return PredictionResponse(
        rain_tomorrow="Yes" if will_rain else "No",
        confidence_score=round(max(rain_probability, 1 - rain_probability), 4),
        rain_probability=round(rain_probability, 4),
        observation_date=observed_on.isoformat(),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": MODEL_PATH.exists()}


@app.get("/meta")
def meta() -> dict:
    return {
        "supported_cities": supported_cities,
        "default_city": DEFAULT_CITY,
        "city_coordinates": city_lookup,
    }


@app.get("/live/city/{city}")
def live_city(city: str) -> dict:
    return fetch_live_snapshot(city)


@app.post("/predict-live", response_model=PredictionResponse)
def predict_live(payload: CityRequest) -> PredictionResponse:
    snapshot = fetch_live_snapshot(payload.city)
    features = {"city": payload.city, **snapshot["current"]}
    observed_on = datetime.fromisoformat(snapshot["observation_date"]).date()
    return predict_from_features(features, observed_on)


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest) -> PredictionResponse:
    observed_on = payload.observation_date or datetime.now().date()
    return predict_from_features(payload.model_dump(), observed_on)
