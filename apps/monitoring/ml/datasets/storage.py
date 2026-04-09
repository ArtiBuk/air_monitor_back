import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_STEPS = [
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
]


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


def _build_metadata_core(
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
        "pipeline": PIPELINE_STEPS,
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
        **_build_metadata_core(
            feature_columns=feature_columns,
            target_columns=target_columns,
            input_len=input_len,
            horizon=horizon,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
            master_df=master_df,
            split_payload=split_payload,
        ),
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)


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
    return _build_metadata_core(
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


def build_output_name(input_len: int, horizon: int) -> str:
    return f"forecast_dataset_{input_len}in_{horizon}out.npz"


def build_metadata_name(input_len: int, horizon: int) -> str:
    return f"forecast_dataset_{input_len}in_{horizon}out.metadata.json"
