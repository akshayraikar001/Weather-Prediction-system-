import os
from datetime import datetime
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
TMP_DIR = BASE_DIR / ".tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Meteostat reads these on import. Keep all cache files inside the workspace.
os.environ["MS_CACHE_DIRECTORY"] = str(TMP_DIR / "meteostat-cache")
os.environ["MS_STATIONS_DB_FILE"] = str(TMP_DIR / "meteostat-stations.db")

from meteostat import Point, config, hourly, stations  # noqa: E402


OUTPUT_PATH = BASE_DIR / "archive" / "india_historical_daily_weather.csv"
START_DATE = datetime(2022, 1, 1)
END_DATE = datetime(2025, 12, 31)

config.block_large_requests = False

CITIES = [
    {"city": "Pune", "state": "Maharashtra", "latitude": 18.5204, "longitude": 73.8567},
    {"city": "Mumbai", "state": "Maharashtra", "latitude": 19.0760, "longitude": 72.8777},
    {"city": "Delhi", "state": "Delhi", "latitude": 28.6139, "longitude": 77.2090},
    {"city": "Jaipur", "state": "Rajasthan", "latitude": 26.9124, "longitude": 75.7873},
    {"city": "Kolkata", "state": "West Bengal", "latitude": 22.5726, "longitude": 88.3639},
    {"city": "Hyderabad", "state": "Telangana", "latitude": 17.3850, "longitude": 78.4867},
    {"city": "Bengaluru", "state": "Karnataka", "latitude": 12.9716, "longitude": 77.5946},
    {"city": "Chennai", "state": "Tamil Nadu", "latitude": 13.0827, "longitude": 80.2707},
    {"city": "Kochi", "state": "Kerala", "latitude": 9.9312, "longitude": 76.2673},
    {"city": "Guwahati", "state": "Assam", "latitude": 26.1445, "longitude": 91.7362},
]


def nearest_station(point: Point) -> tuple[str, pd.Series]:
    station_rows = stations.nearby(point)
    if station_rows.empty:
        raise ValueError("No nearby Meteostat station found")
    station_id = station_rows.index[0]
    return station_id, station_rows.iloc[0]


def aggregate_city(city_info: dict) -> pd.DataFrame:
    point = Point(city_info["latitude"], city_info["longitude"])
    station_id, station = nearest_station(point)

    print(
        f"Downloading {city_info['city']} using station "
        f"{station['name']} ({station_id})"
    )

    fetched = hourly(station_id, START_DATE, END_DATE, timezone="Asia/Kolkata").fetch()

    if fetched is None or fetched.empty:
        raise ValueError(f"No hourly data returned for {city_info['city']}")

    fetched = fetched.copy()
    fetched.columns = [getattr(column, "value", column) for column in fetched.columns]

    daily_df = (
        fetched.resample("D")
        .agg(
            temperature_celsius=("temp", "mean"),
            humidity=("rhum", "mean"),
            pressure_mb=("pres", "mean"),
            wind_speed_kph=("wspd", "mean"),
            gust_kph=("wpgt", "max"),
            cloud_cover=("cldc", "mean"),
            rainfall_mm=("prcp", "sum"),
        )
        .reset_index()
    )

    daily_df.rename(columns={"time": "date"}, inplace=True)
    daily_df["city"] = city_info["city"]
    daily_df["state"] = city_info["state"]
    daily_df["country"] = "India"
    daily_df["latitude"] = city_info["latitude"]
    daily_df["longitude"] = city_info["longitude"]
    daily_df["station_name"] = station["name"]
    daily_df["station_id"] = station_id
    daily_df["station_distance_m"] = station["distance"]
    daily_df["rain_today"] = (daily_df["rainfall_mm"].fillna(0) > 0).astype(int)

    return daily_df[
        [
            "date",
            "city",
            "state",
            "country",
            "latitude",
            "longitude",
            "station_name",
            "station_id",
            "station_distance_m",
            "temperature_celsius",
            "humidity",
            "pressure_mb",
            "wind_speed_kph",
            "gust_kph",
            "cloud_cover",
            "rainfall_mm",
            "rain_today",
        ]
    ]


def main() -> None:
    frames = []
    failures = []

    for city_info in CITIES:
        try:
            city_df = aggregate_city(city_info)
            frames.append(city_df)
            partial_dataset = pd.concat(frames, ignore_index=True)
            partial_dataset.to_csv(OUTPUT_PATH, index=False)
        except Exception as exc:  # pragma: no cover - operational logging
            failures.append(f"{city_info['city']}: {exc}")

    if not frames:
        for failure in failures:
            print(failure)
        raise RuntimeError("No city data could be downloaded")

    dataset = pd.concat(frames, ignore_index=True)
    dataset["date"] = pd.to_datetime(dataset["date"], errors="coerce")
    dataset.sort_values(["city", "date"], inplace=True)
    dataset["rain_tomorrow"] = dataset.groupby("city")["rain_today"].shift(-1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved {len(dataset)} rows to {OUTPUT_PATH}")
    print("Cities downloaded:", dataset["city"].nunique())
    if failures:
        print("Failures:")
        for failure in failures:
            print(f" - {failure}")


if __name__ == "__main__":
    main()
