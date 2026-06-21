import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "archive" / "india_historical_daily_weather.csv"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "rain_tomorrow_model.pkl"
METRICS_PATH = MODEL_DIR / "rain_tomorrow_metrics.json"

FEATURE_COLUMNS = [
    "city",
    "temperature_celsius",
    "humidity",
    "pressure_mb",
    "wind_speed_kph",
    "cloud_cover",
    "rain_today",
    "month",
]
TARGET_COLUMN = "rain_tomorrow"
TRAIN_END_DATE = "2024-12-31"


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df = df.dropna(subset=[TARGET_COLUMN]).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["date"] = df["date"].dt.tz_localize(None)
    df["month"] = df["date"].dt.month
    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(int)
    return df


def build_pipeline() -> Pipeline:
    categorical_features = ["city"]
    numeric_features = [column for column in FEATURE_COLUMNS if column not in categorical_features]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_features,
            ),
            (
                "categorical",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_features,
            ),
        ]
    )

    model = RandomForestClassifier(
        n_estimators=250,
        max_depth=10,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )


def evaluate_model(model: Pipeline, test_df: pd.DataFrame) -> dict:
    predictions = model.predict(test_df[FEATURE_COLUMNS])
    probabilities = model.predict_proba(test_df[FEATURE_COLUMNS])[:, 1]

    report = classification_report(
        test_df[TARGET_COLUMN],
        predictions,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(test_df[TARGET_COLUMN], predictions)

    return {
        "accuracy": accuracy_score(test_df[TARGET_COLUMN], predictions),
        "positive_class_mean_probability": float(probabilities.mean()),
        "confusion_matrix": matrix.tolist(),
        "classification_report": report,
        "test_rows": int(len(test_df)),
        "train_end_date": TRAIN_END_DATE,
        "feature_columns": FEATURE_COLUMNS,
    }


def main() -> None:
    df = load_dataset()
    train_df = df[df["date"] <= pd.Timestamp(TRAIN_END_DATE)].copy()
    test_df = df[df["date"] > pd.Timestamp(TRAIN_END_DATE)].copy()

    if train_df.empty or test_df.empty:
        raise RuntimeError("Time-based split failed. Check the dataset date range.")

    pipeline = build_pipeline()
    pipeline.fit(train_df[FEATURE_COLUMNS], train_df[TARGET_COLUMN])
    metrics = evaluate_model(pipeline, test_df)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": pipeline,
            "feature_columns": FEATURE_COLUMNS,
            "target_column": TARGET_COLUMN,
            "cities": sorted(df["city"].unique().tolist()),
            "train_end_date": TRAIN_END_DATE,
        },
        MODEL_PATH,
    )
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"Saved model to {MODEL_PATH}")
    print(f"Saved metrics to {METRICS_PATH}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")


if __name__ == "__main__":
    main()
