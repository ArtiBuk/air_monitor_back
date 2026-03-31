import pandas as pd

from apps.monitoring.models import Observation

OBSERVATION_COLUMNS = [
    "source",
    "source_kind",
    "station_id",
    "station_name",
    "lat",
    "lon",
    "observed_at_utc",
    "time_bucket_utc",
    "time_window_utc",
    "metric",
    "value",
    "unit",
    "extra",
]


def observations_queryset_to_dataframe(queryset=None) -> pd.DataFrame:
    queryset = queryset or Observation.objects.all()
    rows = list(queryset.values(*OBSERVATION_COLUMNS))
    if not rows:
        return pd.DataFrame(columns=OBSERVATION_COLUMNS)

    frame = pd.DataFrame(rows)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["time_window_utc"] = pd.to_datetime(frame["time_window_utc"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["time_window_utc", "metric", "value"])
    frame = frame.sort_values("time_window_utc").reset_index(drop=True)
    return frame


def build_master_dataset_from_db(queryset=None) -> pd.DataFrame:
    from apps.monitoring.ml.dataset import build_master_from_dataframe

    observations_frame = observations_queryset_to_dataframe(queryset=queryset)
    if observations_frame.empty:
        raise ValueError("No observations found in database.")
    return build_master_from_dataframe(observations_frame)
