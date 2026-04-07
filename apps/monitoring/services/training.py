import logging
from io import BytesIO

from apps.monitoring.models import DatasetSnapshot, ModelVersion

from .dataframes import build_master_dataset_from_db
from .model_selection import ModelSelectionService
from .validation import normalize_feature_columns, normalize_target_columns, validate_dataset_request

logger = logging.getLogger(__name__)


class ModelLifecycleService:
    def build_dataset(
        self,
        *,
        input_len_hours: int,
        forecast_horizon_hours: int,
        feature_columns: list[str] | None = None,
        target_columns: list[str] | None = None,
    ):
        """Собирает и сохраняет срез датасета из наблюдений."""
        from apps.monitoring.ml.dataset import (
            build_metadata_payload,
            create_forecast_windows,
            pack_npz,
            split_by_time,
        )

        logger.info(
            "dataset build started input_len_hours=%s forecast_horizon_hours=%s",
            input_len_hours,
            forecast_horizon_hours,
        )
        feature_columns = normalize_feature_columns(feature_columns)
        target_columns = normalize_target_columns(target_columns)
        master_df = build_master_dataset_from_db()
        validate_dataset_request(
            master_columns=master_df.columns.tolist(),
            master_row_count=len(master_df),
            input_len_hours=input_len_hours,
            forecast_horizon_hours=forecast_horizon_hours,
            feature_columns=feature_columns,
            target_columns=target_columns,
        )
        dataset = create_forecast_windows(
            df=master_df,
            feature_columns=feature_columns,
            target_columns=target_columns,
            input_len=input_len_hours,
            horizon=forecast_horizon_hours,
        )
        split_payload = split_by_time(
            dataset=dataset,
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
        )
        metadata = build_metadata_payload(
            feature_columns=feature_columns,
            target_columns=target_columns,
            input_len=input_len_hours,
            horizon=forecast_horizon_hours,
            train_ratio=0.70,
            val_ratio=0.15,
            test_ratio=0.15,
            master_df=master_df,
            split_payload=split_payload,
        )
        snapshot = DatasetSnapshot.objects.create(
            input_len_hours=input_len_hours,
            forecast_horizon_hours=forecast_horizon_hours,
            master_row_count=len(master_df),
            sample_count=(len(split_payload["X_train"]) + len(split_payload["X_val"]) + len(split_payload["X_test"])),
            feature_columns=feature_columns,
            target_columns=target_columns,
            metadata=metadata,
            payload_npz=pack_npz(split_payload),
        )
        return snapshot

    def train(
        self,
        *,
        dataset_snapshot=None,
        requested_by=None,
        epochs: int,
        batch_size: int,
        lr: float,
        weight_decay: float,
        patience: int,
        seed: int,
    ):
        """Обучает и сохраняет версию модели по срезу датасета."""
        import torch

        from apps.monitoring.ml.dataset import unpack_npz
        from apps.monitoring.ml.training import build_evaluation_metrics, predict, set_seed, train_model

        logger.info(
            "training started epochs=%s batch_size=%s lr=%s weight_decay=%s patience=%s seed=%s",
            epochs,
            batch_size,
            lr,
            weight_decay,
            patience,
            seed,
        )
        snapshot = dataset_snapshot or DatasetSnapshot.objects.order_by("-created_at").first()
        if snapshot is None:
            snapshot = self.build_dataset(input_len_hours=72, forecast_horizon_hours=24)

        data = unpack_npz(snapshot.payload_npz)

        set_seed(seed)
        torch.set_num_threads(1)
        device = "cuda" if torch.cuda.is_available() else "cpu"

        model_version = ModelVersion.objects.create(
            dataset=snapshot,
            requested_by=requested_by,
            name=f"model-{snapshot.created_at:%Y%m%d%H%M%S}",
            status=ModelVersion.Status.TRAINING,
            input_len_hours=snapshot.input_len_hours,
            forecast_horizon_hours=snapshot.forecast_horizon_hours,
            feature_names=data["feature_names"].tolist(),
            target_names=data["target_names"].tolist(),
            training_config={
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "weight_decay": weight_decay,
                "patience": patience,
                "seed": seed,
                "device": device,
            },
        )

        try:
            artifacts = train_model(
                x_train=data["X_train"].astype("float32"),
                y_train=data["y_train"].astype("float32"),
                x_val=data["X_val"].astype("float32"),
                y_val=data["y_val"].astype("float32"),
                target_names=data["target_names"],
                batch_size=batch_size,
                epochs=epochs,
                lr=lr,
                weight_decay=weight_decay,
                patience=patience,
                device=device,
            )
            y_pred_test = predict(
                artifacts.model,
                data["X_test"].astype("float32"),
                artifacts.x_scaler,
                artifacts.y_mean,
                artifacts.y_std,
                device,
            )
            y_pred_test = y_pred_test.clip(min=0.0)
            metrics = build_evaluation_metrics(
                data["y_test"].astype("float32"),
                y_pred_test,
                data["target_names"],
            )

            buffer = BytesIO()
            torch.save(
                {
                    "model_state_dict": artifacts.model.state_dict(),
                    "feature_names": data["feature_names"].tolist(),
                    "target_names": data["target_names"].tolist(),
                    "x_mean": artifacts.x_scaler.mean,
                    "x_std": artifacts.x_scaler.std,
                    "y_mean": artifacts.y_mean,
                    "y_std": artifacts.y_std,
                    "model_config": {
                        "input_dim": len(data["feature_names"]),
                        "output_dim": len(data["target_names"]),
                        "horizon": artifacts.model.horizon,
                        "hidden_dim": artifacts.model.hidden_dim,
                        "num_layers": artifacts.model.num_layers,
                        "dropout": artifacts.model.dropout,
                    },
                },
                buffer,
            )

            model_version.status = ModelVersion.Status.READY
            model_version.metrics = metrics
            model_version.history = artifacts.history
            model_version.checkpoint_blob = buffer.getvalue()
            model_version.is_active = False
            model_version.save(
                update_fields=[
                    "status",
                    "metrics",
                    "history",
                    "checkpoint_blob",
                    "is_active",
                    "updated_at",
                ]
            )
            best_model = ModelSelectionService().ensure_best_model_is_active()
            model_version.is_active = best_model is not None and best_model.id == model_version.id
        except Exception as exc:
            model_version.status = ModelVersion.Status.FAILED
            model_version.error_message = str(exc)
            model_version.save(update_fields=["status", "error_message", "updated_at"])
            raise

        return model_version
