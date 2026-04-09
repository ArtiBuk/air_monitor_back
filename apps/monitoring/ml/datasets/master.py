import numpy as np
import pandas as pd

from .config import BASE_SIGNAL_COLUMNS, COUNT_COLUMNS, INPUT_CSV, RNG


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
    wide = grouped.pivot(index="time_window_utc", columns="metric", values="value").reset_index()

    wide.columns.name = None
    return wide.rename(
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

    return (
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


def build_hourly_analytics(observations_df: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(
        build_mycity_agg(observations_df),
        build_plume_wide(observations_df),
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

    return df.set_index("timestamp_utc").reindex(full_index).rename_axis("timestamp_utc").reset_index()


def add_missing_flags(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    for col in BASE_SIGNAL_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan
        result[f"{col}_missing"] = result[col].isna().astype("int8")

    return result


def fill_short_gaps(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    numeric_cols = [column for column in BASE_SIGNAL_COLUMNS if column not in COUNT_COLUMNS]

    for col in numeric_cols:
        if col in result.columns:
            result[col] = result[col].interpolate(method="linear", limit=3, limit_direction="both")

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
    missing_cols = [f"{column}_missing" for column in BASE_SIGNAL_COLUMNS if f"{column}_missing" in result.columns]

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

    return result.sort_values("timestamp_utc").reset_index(drop=True)


def build_master_from_observations(input_csv: str = INPUT_CSV) -> pd.DataFrame:
    return build_master_from_dataframe(load_observations(input_csv))


def build_master_from_dataframe(obs: pd.DataFrame) -> pd.DataFrame:
    full = build_full_hourly_index(build_hourly_analytics(obs))
    full = add_missing_flags(full)
    full = fill_short_gaps(full)
    full = enrich_missing_features(full)
    full = add_time_features(full)
    full = add_quality_features(full)
    return finalize_master_dataset(full)
