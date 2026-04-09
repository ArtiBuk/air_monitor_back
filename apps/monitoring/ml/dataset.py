from pathlib import Path

from .datasets import (
    BASE_SIGNAL_COLUMNS,
    COUNT_COLUMNS,
    DEFAULT_FEATURE_COLUMNS,
    DEFAULT_TARGET_COLUMNS,
    INPUT_CSV,
    OUTPUT_DIR,
    build_master_from_dataframe,
    build_master_from_observations,
    build_metadata_name,
    build_metadata_payload,
    build_output_name,
    create_forecast_windows,
    pack_npz,
    save_metadata,
    save_npz,
    split_by_time,
    unpack_npz,
)

__all__ = [
    "BASE_SIGNAL_COLUMNS",
    "COUNT_COLUMNS",
    "DEFAULT_FEATURE_COLUMNS",
    "DEFAULT_TARGET_COLUMNS",
    "INPUT_CSV",
    "OUTPUT_DIR",
    "build_master_from_dataframe",
    "build_master_from_observations",
    "build_metadata_name",
    "build_metadata_payload",
    "build_output_name",
    "create_forecast_windows",
    "main",
    "pack_npz",
    "save_metadata",
    "save_npz",
    "split_by_time",
    "unpack_npz",
]


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
