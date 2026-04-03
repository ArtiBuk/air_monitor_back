import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

INPUT_CSV = "data/observations.csv"
OUTPUT_DIR = "data"


RNG = np.random.default_rng(42)

BASE_SIGNAL_COLUMNS = [
    "mycityair_aqi_mean",
    "mycityair_aqi_max",
    "mycityair_aqi_min",
    "mycityair_station_count",
    "mycityair_obs_count",
    "plume_index",
    "plume_pm25",
    "plume_pm10",
    "plume_no2",
    "plume_so2",
    "plume_o3",
    "plume_co",
]

COUNT_COLUMNS = [
    "mycityair_station_count",
    "mycityair_obs_count",
]

DEFAULT_FEATURE_COLUMNS = [
    "mycityair_aqi_mean",
    "mycityair_aqi_max",
    "mycityair_aqi_min",
    "mycityair_station_count",
    "mycityair_obs_count",
    "plume_index",
    "plume_pm25",
    "plume_pm10",
    "plume_no2",
    "plume_so2",
    "plume_o3",
    "plume_co",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
    "month_sin",
    "month_cos",
    "day_of_year_sin",
    "day_of_year_cos",
    "is_weekend",
    "missing_count_total",
    "missing_ratio_total",
    "mycityair_aqi_mean_missing",
    "mycityair_aqi_max_missing",
    "mycityair_aqi_min_missing",
    "plume_index_missing",
    "plume_pm25_missing",
    "plume_pm10_missing",
    "plume_no2_missing",
    "plume_so2_missing",
    "plume_o3_missing",
    "plume_co_missing",
]

DEFAULT_TARGET_COLUMNS = [
    "mycityair_aqi_mean",
    "plume_pm25",
    "plume_pm10",
    "plume_no2",
    "plume_so2",
    "plume_o3",
    "plume_co",
    "plume_index",
]


def load_observations(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    required_columns = {"source", "time_window_utc", "metric", "value"}
    missing = sorted(required_columns - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns in observations.csv: {missing}")

    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["time_window_utc", "metric", "value"])
    df["time_window_utc"] = pd.to_datetime(df["time_window_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["time_window_utc"])
    df = df.sort_values("time_window_utc").reset_index(drop=True)

    return df


def build_plume_wide(df: pd.DataFrame) -> pd.DataFrame:
    plume = df[df["source"] == "plumelabs"].copy()
    if plume.empty:
        return pd.DataFrame(columns=["timestamp_utc"])

    grouped = plume.groupby(["time_window_utc", "metric"], as_index=False)["value"].mean()

    wide = grouped.pivot(
        index="time_window_utc",
        columns="metric",
        values="value",
    ).reset_index()

    wide.columns.name = None
    wide = wide.rename(
        columns={
            "time_window_utc": "timestamp_utc",
            "plume_index": "plume_index",
            "pm25": "plume_pm25",
            "pm10": "plume_pm10",
            "no2": "plume_no2",
            "so2": "plume_so2",
            "o3": "plume_o3",
            "co": "plume_co",
        }
    )

    return wide


def build_mycity_agg(df: pd.DataFrame) -> pd.DataFrame:
    mycity = df[(df["source"] == "mycityair") & (df["metric"] == "aqi")].copy()

    if mycity.empty:
        return pd.DataFrame(
            columns=[
                "timestamp_utc",
                "mycityair_aqi_mean",
                "mycityair_aqi_max",
                "mycityair_aqi_min",
                "mycityair_station_count",
                "mycityair_obs_count",
            ]
        )

    grouped = (
        mycity.groupby("time_window_utc")
        .agg(
            mycityair_aqi_mean=("value", "mean"),
            mycityair_aqi_max=("value", "max"),
            mycityair_aqi_min=("value", "min"),
            mycityair_station_count=("station_id", "nunique"),
            mycityair_obs_count=("value", "count"),
        )
        .reset_index()
        .rename(columns={"time_window_utc": "timestamp_utc"})
    )

    return grouped


def build_hourly_analytics(observations_df: pd.DataFrame) -> pd.DataFrame:
    plume_wide = build_plume_wide(observations_df)
    mycity_agg = build_mycity_agg(observations_df)

    merged = pd.merge(
        mycity_agg,
        plume_wide,
        on="timestamp_utc",
        how="outer",
    )

    for col in BASE_SIGNAL_COLUMNS:
        if col not in merged.columns:
            merged[col] = np.nan

    merged = merged.sort_values("timestamp_utc").drop_duplicates(subset=["timestamp_utc"], keep="last")
    merged = merged.reset_index(drop=True)

    for col in BASE_SIGNAL_COLUMNS:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")

    return merged


def build_full_hourly_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        raise ValueError("No data after hourly aggregation")

    start_ts = df["timestamp_utc"].min().floor("h")
    end_ts = df["timestamp_utc"].max().floor("h")

    full_index = pd.date_range(start=start_ts, end=end_ts, freq="1h", tz="UTC")

    result = df.set_index("timestamp_utc").reindex(full_index).rename_axis("timestamp_utc").reset_index()

    return result


def add_missing_flags(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    for col in BASE_SIGNAL_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan
        result[f"{col}_missing"] = result[col].isna().astype("int8")

    return result


def fill_short_gaps(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    numeric_cols = [c for c in BASE_SIGNAL_COLUMNS if c not in COUNT_COLUMNS]
    for col in numeric_cols:
        if col in result.columns:
            result[col] = result[col].interpolate(
                method="linear",
                limit=3,
                limit_direction="both",
            )

    for col in COUNT_COLUMNS:
        if col in result.columns:
            result[col] = result[col].ffill(limit=3).bfill(limit=3)

    return result


def enrich_missing_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    if "plume_so2" in result.columns:
        mask = result["plume_so2"].isna()
        base = (
            0.45 * result["plume_pm10"].fillna(result["plume_pm10"].median())
            + 0.35 * result["plume_pm25"].fillna(result["plume_pm25"].median())
            + 0.20 * result["plume_no2"].fillna(result["plume_no2"].median())
        )
        noise = RNG.normal(0, max(float(base.std(skipna=True) or 0.0), 1.0) * 0.10, size=len(result))
        result.loc[mask, "plume_so2"] = (base + noise).clip(lower=0)

    if "plume_co" in result.columns:
        mask = result["plume_co"].isna()
        base = 0.60 * result["plume_no2"].fillna(result["plume_no2"].median()) + 0.40 * result["plume_pm25"].fillna(
            result["plume_pm25"].median()
        )
        noise = RNG.normal(0, max(float(base.std(skipna=True) or 0.0), 1.0) * 0.08, size=len(result))
        result.loc[mask, "plume_co"] = (base + noise).clip(lower=0)

    if "plume_index" in result.columns:
        pm25 = result["plume_pm25"].fillna(result["plume_pm25"].median())
        pm10 = result["plume_pm10"].fillna(result["plume_pm10"].median())
        no2 = result["plume_no2"].fillna(result["plume_no2"].median())
        o3 = result["plume_o3"].fillna(result["plume_o3"].median())

        idx_mask = result["plume_index"].isna()
        rebuilt_index = 0.35 * pm25 + 0.30 * pm10 + 0.20 * no2 + 0.15 * o3
        result.loc[idx_mask, "plume_index"] = rebuilt_index[idx_mask]

    if "mycityair_station_count" in result.columns:
        mask = result["mycityair_station_count"].isna()
        base = 4 + RNG.integers(-1, 2, len(result))
        result.loc[mask, "mycityair_station_count"] = np.clip(base[mask], 2, 6)

    if "mycityair_obs_count" in result.columns:
        mask = result["mycityair_obs_count"].isna()
        station_counts = result["mycityair_station_count"].fillna(4).to_numpy()
        mult = RNG.integers(3, 8, len(result))
        result.loc[mask, "mycityair_obs_count"] = station_counts[mask] * mult[mask]

    for col in BASE_SIGNAL_COLUMNS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    return result


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    ts = result["timestamp_utc"]

    result["date_utc"] = ts.dt.strftime("%Y-%m-%d")
    result["hour"] = ts.dt.hour.astype("int16")
    result["weekday"] = ts.dt.weekday.astype("int16")
    result["month"] = ts.dt.month.astype("int16")
    result["day_of_year"] = ts.dt.dayofyear.astype("int16")
    result["is_weekend"] = (result["weekday"] >= 5).astype("int8")

    result["hour_sin"] = np.sin(2 * np.pi * result["hour"] / 24.0)
    result["hour_cos"] = np.cos(2 * np.pi * result["hour"] / 24.0)

    result["weekday_sin"] = np.sin(2 * np.pi * result["weekday"] / 7.0)
    result["weekday_cos"] = np.cos(2 * np.pi * result["weekday"] / 7.0)

    result["month_sin"] = np.sin(2 * np.pi * (result["month"] - 1) / 12.0)
    result["month_cos"] = np.cos(2 * np.pi * (result["month"] - 1) / 12.0)

    result["day_of_year_sin"] = np.sin(2 * np.pi * (result["day_of_year"] - 1) / 366.0)
    result["day_of_year_cos"] = np.cos(2 * np.pi * (result["day_of_year"] - 1) / 366.0)

    return result


def add_quality_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    missing_cols = [f"{c}_missing" for c in BASE_SIGNAL_COLUMNS if f"{c}_missing" in result.columns]
    if missing_cols:
        result["missing_count_total"] = result[missing_cols].sum(axis=1).astype("int16")
        result["missing_ratio_total"] = result[missing_cols].mean(axis=1).astype("float32")
    else:
        result["missing_count_total"] = 0
        result["missing_ratio_total"] = 0.0

    return result


def finalize_master_dataset(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    for col in COUNT_COLUMNS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce").round()
            result[col] = result[col].ffill().bfill()
            result[col] = result[col].astype("int32")

    for col in BASE_SIGNAL_COLUMNS:
        if col in result.columns and col not in COUNT_COLUMNS:
            result[col] = pd.to_numeric(result[col], errors="coerce")
            result[col] = result[col].interpolate(method="linear", limit_direction="both")
            result[col] = result[col].ffill().bfill()

    for col in result.columns:
        if col.endswith("_missing"):
            result[col] = pd.to_numeric(result[col], errors="coerce").fillna(1).astype("int8")

    result = result.sort_values("timestamp_utc").reset_index(drop=True)
    return result


def build_master_from_observations(input_csv: str = INPUT_CSV) -> pd.DataFrame:
    obs = load_observations(input_csv)
    return build_master_from_dataframe(obs)


def build_master_from_dataframe(obs: pd.DataFrame) -> pd.DataFrame:
    hourly = build_hourly_analytics(obs)
    full = build_full_hourly_index(hourly)
    full = add_missing_flags(full)
    full = fill_short_gaps(full)
    full = enrich_missing_features(full)
    full = add_time_features(full)
    full = add_quality_features(full)
    full = finalize_master_dataset(full)

    return full


def validate_columns(df: pd.DataFrame, feature_columns: list[str], target_columns: list[str]) -> None:
    required = set(feature_columns) | set(target_columns) | {"timestamp_utc"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def prepare_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = df.copy()

    for col in columns:
        result[col] = pd.to_numeric(result[col], errors="coerce")

        if col.endswith("_missing"):
            result[col] = result[col].fillna(1).astype(np.float32)
            continue

        result[col] = result[col].interpolate(method="linear", limit_direction="both")
        result[col] = result[col].ffill().bfill()

        if result[col].isna().all():
            result[col] = 0.0

    return result


def build_sample_validity_mask(
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    input_len: int,
    horizon: int,
    max_missing_ratio_x: float = 0.20,
    max_missing_ratio_y: float = 0.00,
) -> np.ndarray:
    feature_na = df[feature_columns].isna().mean(axis=1).to_numpy(dtype=np.float32)
    target_na = df[target_columns].isna().mean(axis=1).to_numpy(dtype=np.float32)

    n_rows = len(df)
    n_samples = n_rows - input_len - horizon + 1

    if n_samples <= 0:
        return np.array([], dtype=bool)

    valid = np.ones(n_samples, dtype=bool)

    for i in range(n_samples):
        x_slice = feature_na[i : i + input_len]
        y_slice = target_na[i + input_len : i + input_len + horizon]

        if x_slice.mean() > max_missing_ratio_x:
            valid[i] = False
            continue

        if y_slice.mean() > max_missing_ratio_y:
            valid[i] = False
            continue

    return valid


def create_forecast_windows(
    df: pd.DataFrame,
    feature_columns: list[str],
    target_columns: list[str],
    input_len: int,
    horizon: int,
    max_missing_ratio_x: float = 0.20,
    max_missing_ratio_y: float = 0.00,
) -> dict:
    validate_columns(df, feature_columns, target_columns)

    raw_df = df.copy()
    numeric_df = prepare_numeric_columns(raw_df, feature_columns + target_columns)

    valid_mask = build_sample_validity_mask(
        raw_df,
        feature_columns=feature_columns,
        target_columns=target_columns,
        input_len=input_len,
        horizon=horizon,
        max_missing_ratio_x=max_missing_ratio_x,
        max_missing_ratio_y=max_missing_ratio_y,
    )

    timestamps = raw_df["timestamp_utc"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy(dtype="datetime64[ns]")
    x_values = numeric_df[feature_columns].to_numpy(dtype=np.float32)
    y_values = numeric_df[target_columns].to_numpy(dtype=np.float32)

    n_rows = len(raw_df)
    n_samples = n_rows - input_len - horizon + 1

    X_list = []
    y_list = []
    input_start_ts = []
    input_end_ts = []
    target_start_ts = []
    target_end_ts = []

    for i in range(n_samples):
        if not valid_mask[i]:
            continue

        x_window = x_values[i : i + input_len]
        y_window = y_values[i + input_len : i + input_len + horizon]

        X_list.append(x_window)
        y_list.append(y_window)

        input_start_ts.append(timestamps[i])
        input_end_ts.append(timestamps[i + input_len - 1])
        target_start_ts.append(timestamps[i + input_len])
        target_end_ts.append(timestamps[i + input_len + horizon - 1])

    if not X_list:
        raise ValueError("No valid windows were created. Check missing values and window sizes.")

    dataset = {
        "X": np.stack(X_list).astype(np.float32),
        "y": np.stack(y_list).astype(np.float32),
        "input_start_ts": np.array(input_start_ts, dtype="datetime64[ns]"),
        "input_end_ts": np.array(input_end_ts, dtype="datetime64[ns]"),
        "target_start_ts": np.array(target_start_ts, dtype="datetime64[ns]"),
        "target_end_ts": np.array(target_end_ts, dtype="datetime64[ns]"),
        "feature_names": np.array(feature_columns, dtype=object),
        "target_names": np.array(target_columns, dtype=object),
    }

    return dataset


def split_by_time(
    dataset: dict,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> dict:
    ratio_sum = train_ratio + val_ratio + test_ratio
    if not np.isclose(ratio_sum, 1.0):
        raise ValueError("train_ratio + val_ratio + test_ratio must equal 1.0")

    n = len(dataset["X"])
    if n < 3:
        raise ValueError("Not enough samples to split dataset")

    train_end = min(max(1, int(n * train_ratio)), n - 2)
    val_end = min(max(train_end + 1, int(n * (train_ratio + val_ratio))), n - 1)

    result = {
        "X_train": dataset["X"][:train_end],
        "y_train": dataset["y"][:train_end],
        "X_val": dataset["X"][train_end:val_end],
        "y_val": dataset["y"][train_end:val_end],
        "X_test": dataset["X"][val_end:],
        "y_test": dataset["y"][val_end:],
        "input_start_ts_train": dataset["input_start_ts"][:train_end],
        "input_end_ts_train": dataset["input_end_ts"][:train_end],
        "target_start_ts_train": dataset["target_start_ts"][:train_end],
        "target_end_ts_train": dataset["target_end_ts"][:train_end],
        "input_start_ts_val": dataset["input_start_ts"][train_end:val_end],
        "input_end_ts_val": dataset["input_end_ts"][train_end:val_end],
        "target_start_ts_val": dataset["target_start_ts"][train_end:val_end],
        "target_end_ts_val": dataset["target_end_ts"][train_end:val_end],
        "input_start_ts_test": dataset["input_start_ts"][val_end:],
        "input_end_ts_test": dataset["input_end_ts"][val_end:],
        "target_start_ts_test": dataset["target_start_ts"][val_end:],
        "target_end_ts_test": dataset["target_end_ts"][val_end:],
        "feature_names": dataset["feature_names"],
        "target_names": dataset["target_names"],
    }

    return result


def save_npz(path: str, payload: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)


def pack_npz(payload: dict) -> bytes:
    buffer = BytesIO()
    np.savez_compressed(buffer, **payload)
    return buffer.getvalue()


def unpack_npz(payload_bytes: bytes) -> dict:
    with BytesIO(payload_bytes) as buffer:
        data = np.load(buffer, allow_pickle=True)
        return {key: data[key] for key in data.files}


def save_metadata(
    path: str,
    *,
    input_csv: str,
    output_npz: str,
    feature_columns: list[str],
    target_columns: list[str],
    input_len: int,
    horizon: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    master_df: pd.DataFrame,
    split_payload: dict,
) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "input_csv": input_csv,
        "output_npz": output_npz,
        "source_stage_count": 1,
        "pipeline": [
            "observations_csv",
            "hourly_aggregation",
            "full_hourly_index",
            "missing_flags",
            "short_gap_fill",
            "feature_reconstruction",
            "time_features",
            "quality_features",
            "window_generation",
            "time_split",
        ],
        "master_row_count": int(len(master_df)),
        "master_timestamp_min_utc": (
            master_df["timestamp_utc"].min().strftime("%Y-%m-%dT%H:%M:%SZ") if not master_df.empty else None
        ),
        "master_timestamp_max_utc": (
            master_df["timestamp_utc"].max().strftime("%Y-%m-%dT%H:%M:%SZ") if not master_df.empty else None
        ),
        "input_len_hours": input_len,
        "forecast_horizon_hours": horizon,
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "split": {
            "train_ratio": train_ratio,
            "val_ratio": val_ratio,
            "test_ratio": test_ratio,
        },
        "shapes": {
            "X_train": list(split_payload["X_train"].shape),
            "y_train": list(split_payload["y_train"].shape),
            "X_val": list(split_payload["X_val"].shape),
            "y_val": list(split_payload["y_val"].shape),
            "X_test": list(split_payload["X_test"].shape),
            "y_test": list(split_payload["y_test"].shape),
        },
        "sample_counts": {
            "train": int(len(split_payload["X_train"])),
            "val": int(len(split_payload["X_val"])),
            "test": int(len(split_payload["X_test"])),
            "total": int(len(split_payload["X_train"]) + len(split_payload["X_val"]) + len(split_payload["X_test"])),
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def build_metadata_payload(
    *,
    feature_columns: list[str],
    target_columns: list[str],
    input_len: int,
    horizon: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    master_df: pd.DataFrame,
    split_payload: dict,
) -> dict:
    return {
        "pipeline": [
            "observations_db",
            "hourly_aggregation",
            "full_hourly_index",
            "missing_flags",
            "short_gap_fill",
            "feature_reconstruction",
            "time_features",
            "quality_features",
            "window_generation",
            "time_split",
        ],
        "master_row_count": int(len(master_df)),
        "master_timestamp_min_utc": (
            master_df["timestamp_utc"].min().strftime("%Y-%m-%dT%H:%M:%SZ") if not master_df.empty else None
        ),
        "master_timestamp_max_utc": (
            master_df["timestamp_utc"].max().strftime("%Y-%m-%dT%H:%M:%SZ") if not master_df.empty else None
        ),
        "input_len_hours": input_len,
        "forecast_horizon_hours": horizon,
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "split": {
            "train_ratio": train_ratio,
            "val_ratio": val_ratio,
            "test_ratio": test_ratio,
        },
        "shapes": {
            "X_train": list(split_payload["X_train"].shape),
            "y_train": list(split_payload["y_train"].shape),
            "X_val": list(split_payload["X_val"].shape),
            "y_val": list(split_payload["y_val"].shape),
            "X_test": list(split_payload["X_test"].shape),
            "y_test": list(split_payload["y_test"].shape),
        },
        "sample_counts": {
            "train": int(len(split_payload["X_train"])),
            "val": int(len(split_payload["X_val"])),
            "test": int(len(split_payload["X_test"])),
            "total": int(len(split_payload["X_train"]) + len(split_payload["X_val"]) + len(split_payload["X_test"])),
        },
    }


def build_output_name(input_len: int, horizon: int) -> str:
    return f"forecast_dataset_{input_len}in_{horizon}out.npz"


def build_metadata_name(input_len: int, horizon: int) -> str:
    return f"forecast_dataset_{input_len}in_{horizon}out.metadata.json"


def main():
    input_len = 72
    horizon = 24
    train_ratio = 0.70
    val_ratio = 0.15
    test_ratio = 0.15

    feature_columns = DEFAULT_FEATURE_COLUMNS
    target_columns = DEFAULT_TARGET_COLUMNS

    output_npz = str(Path(OUTPUT_DIR) / build_output_name(input_len, horizon))
    output_metadata = str(Path(OUTPUT_DIR) / build_metadata_name(input_len, horizon))

    master_df = build_master_from_observations(INPUT_CSV)

    dataset = create_forecast_windows(
        df=master_df,
        feature_columns=feature_columns,
        target_columns=target_columns,
        input_len=input_len,
        horizon=horizon,
        max_missing_ratio_x=0.20,
        max_missing_ratio_y=0.00,
    )

    split_payload = split_by_time(
        dataset=dataset,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
    )

    save_npz(output_npz, split_payload)

    save_metadata(
        output_metadata,
        input_csv=INPUT_CSV,
        output_npz=output_npz,
        feature_columns=feature_columns,
        target_columns=target_columns,
        input_len=input_len,
        horizon=horizon,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        master_df=master_df,
        split_payload=split_payload,
    )

    print("Forecast dataset saved:")
    print(f"  NPZ:      {output_npz}")
    print(f"  METADATA: {output_metadata}")
    print()
    print("Master dataframe shape:")
    print(master_df.shape)
    print()
    print("Shapes:")
    print(f"  X_train: {split_payload['X_train'].shape}")
    print(f"  y_train: {split_payload['y_train'].shape}")
    print(f"  X_val:   {split_payload['X_val'].shape}")
    print(f"  y_val:   {split_payload['y_val'].shape}")
    print(f"  X_test:  {split_payload['X_test'].shape}")
    print(f"  y_test:  {split_payload['y_test'].shape}")
    print()
    print("Features:")
    print(list(split_payload["feature_names"]))
    print()
    print("Targets:")
    print(list(split_payload["target_names"]))


if __name__ == "__main__":
    main()
