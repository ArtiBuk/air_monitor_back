import numpy as np
import pandas as pd


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

    n_samples = len(df) - input_len - horizon + 1
    if n_samples <= 0:
        return np.array([], dtype=bool)

    valid = np.ones(n_samples, dtype=bool)
    for index in range(n_samples):
        x_slice = feature_na[index : index + input_len]
        y_slice = target_na[index + input_len : index + input_len + horizon]

        if x_slice.mean() > max_missing_ratio_x or y_slice.mean() > max_missing_ratio_y:
            valid[index] = False

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
    n_samples = len(raw_df) - input_len - horizon + 1

    x_list = []
    y_list = []
    input_start_ts = []
    input_end_ts = []
    target_start_ts = []
    target_end_ts = []

    for index in range(n_samples):
        if not valid_mask[index]:
            continue

        x_list.append(x_values[index : index + input_len])
        y_list.append(y_values[index + input_len : index + input_len + horizon])
        input_start_ts.append(timestamps[index])
        input_end_ts.append(timestamps[index + input_len - 1])
        target_start_ts.append(timestamps[index + input_len])
        target_end_ts.append(timestamps[index + input_len + horizon - 1])

    if not x_list:
        raise ValueError("No valid windows were created. Check missing values and window sizes.")

    return {
        "X": np.stack(x_list).astype(np.float32),
        "y": np.stack(y_list).astype(np.float32),
        "input_start_ts": np.array(input_start_ts, dtype="datetime64[ns]"),
        "input_end_ts": np.array(input_end_ts, dtype="datetime64[ns]"),
        "target_start_ts": np.array(target_start_ts, dtype="datetime64[ns]"),
        "target_end_ts": np.array(target_end_ts, dtype="datetime64[ns]"),
        "feature_names": np.array(feature_columns, dtype=object),
        "target_names": np.array(target_columns, dtype=object),
    }


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

    return {
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
