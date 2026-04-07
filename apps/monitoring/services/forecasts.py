import logging
from dataclasses import dataclass

from django.db import transaction

from apps.monitoring.models import ForecastRecord, ForecastRun

from .dataframes import build_master_dataset_from_db
from .model_selection import ModelSelectionService
from .utils import parse_utc_datetime

logger = logging.getLogger(__name__)


@dataclass
class ForecastGenerationResult:
    run_id: str
    generated_from_timestamp_utc: str
    forecast_horizon_hours: int
    records: list[dict]


class ForecastService:
    @transaction.atomic
    def generate(
        self,
        *,
        requested_by=None,
        input_len_hours=None,
        forecast_horizon_hours=None,
        model_version=None,
        generated_from_timestamp_utc=None,
    ) -> ForecastGenerationResult:
        """Строит прогноз от последнего или исторического окна наблюдений."""
        import pandas as pd

        from apps.monitoring.ml import AirForecaster

        model_version = model_version or ModelSelectionService().ensure_best_model_is_active()
        if model_version is None or not model_version.checkpoint_blob:
            raise ValueError("No active trained model found in database.")

        forecast_horizon_hours = forecast_horizon_hours or model_version.forecast_horizon_hours
        input_len_hours = input_len_hours or model_version.input_len_hours

        if forecast_horizon_hours != model_version.forecast_horizon_hours:
            raise ValueError(
                "Requested forecast horizon does not match trained model horizon: "
                f"requested={forecast_horizon_hours}, model={model_version.forecast_horizon_hours}"
            )
        if input_len_hours != model_version.input_len_hours:
            raise ValueError(
                "Requested input window does not match trained model input window: "
                f"requested={input_len_hours}, model={model_version.input_len_hours}"
            )

        logger.info(
            "forecast generation started requested_by=%s input_len_hours=%s forecast_horizon_hours=%s",
            getattr(requested_by, "id", None),
            input_len_hours,
            forecast_horizon_hours,
        )

        run = ForecastRun.objects.create(
            requested_by=requested_by,
            model_version=model_version,
            status=ForecastRun.Status.STARTED,
            forecast_horizon_hours=forecast_horizon_hours,
        )

        try:
            master_df = build_master_dataset_from_db()
            if generated_from_timestamp_utc is not None:
                cutoff_timestamp = pd.Timestamp(generated_from_timestamp_utc)
                if cutoff_timestamp.tzinfo is None:
                    cutoff_timestamp = cutoff_timestamp.tz_localize("UTC")
                else:
                    cutoff_timestamp = cutoff_timestamp.tz_convert("UTC")
                master_df = master_df[master_df["timestamp_utc"] <= cutoff_timestamp].copy()
                if master_df.empty:
                    raise ValueError("No historical rows found for the requested forecast base timestamp.")

            feature_columns = list(model_version.feature_names)

            missing = sorted(set(feature_columns) - set(master_df.columns))
            if missing:
                raise ValueError(f"Master dataset is missing feature columns: {missing}")

            if len(master_df) < input_len_hours:
                raise ValueError(
                    f"Not enough hourly rows for forecast: need at least {input_len_hours}, got {len(master_df)}"
                )

            latest_window = master_df[feature_columns].tail(input_len_hours).to_numpy(dtype="float32")
            latest_timestamp = pd.Timestamp(master_df["timestamp_utc"].iloc[-1])
            forecaster = AirForecaster(checkpoint_blob=bytes(model_version.checkpoint_blob), device="cpu")
            pred = forecaster.predict_next24(latest_window)

            future_index = pd.date_range(
                start=latest_timestamp + pd.Timedelta(hours=1),
                periods=forecast_horizon_hours,
                freq="1h",
                tz="UTC",
            )
            records = []
            for i, ts in enumerate(future_index):
                row = {"timestamp_utc": ts.isoformat().replace("+00:00", "Z")}
                for target_idx, target_name in enumerate(forecaster.target_names):
                    row[target_name] = float(pred[i, target_idx])
                records.append(row)
        except Exception as exc:
            run.status = ForecastRun.Status.FAILED
            run.error_message = str(exc)
            run.save(update_fields=["status", "error_message", "updated_at"])
            logger.exception("forecast generation failed run_id=%s", run.id)
            raise

        ForecastRecord.objects.bulk_create(
            [
                ForecastRecord(
                    forecast_run=run,
                    timestamp_utc=parse_utc_datetime(item["timestamp_utc"]),
                    values={key: value for key, value in item.items() if key != "timestamp_utc"},
                )
                for item in records
            ]
        )

        run.status = ForecastRun.Status.SUCCESS
        run.generated_from_timestamp_utc = parse_utc_datetime(latest_timestamp.isoformat().replace("+00:00", "Z"))
        run.metadata = {"record_count": len(records)}
        run.save(update_fields=["status", "generated_from_timestamp_utc", "metadata", "updated_at"])
        logger.info("forecast generation completed run_id=%s records=%s", run.id, len(records))

        return ForecastGenerationResult(
            run_id=str(run.id),
            generated_from_timestamp_utc=latest_timestamp.isoformat().replace("+00:00", "Z"),
            forecast_horizon_hours=forecast_horizon_hours,
            records=records,
        )
