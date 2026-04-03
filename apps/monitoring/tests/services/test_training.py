import pytest

from apps.monitoring.ml.dataset import split_by_time
from apps.monitoring.services.training import ModelLifecycleService

pytestmark = pytest.mark.django_db


def test_build_dataset_rejects_empty_feature_columns(reference_observations_factory):
    reference_observations_factory(hours=168)

    with pytest.raises(ValueError, match="feature_columns не может быть пустым"):
        ModelLifecycleService().build_dataset(
            input_len_hours=72,
            forecast_horizon_hours=24,
            feature_columns=[],
            target_columns=["plume_pm25"],
        )


def test_build_dataset_rejects_unknown_target_columns(reference_observations_factory):
    reference_observations_factory(hours=168)

    with pytest.raises(ValueError, match="В master dataset отсутствуют таргеты"):
        ModelLifecycleService().build_dataset(
            input_len_hours=72,
            forecast_horizon_hours=24,
            target_columns=["unknown_target"],
        )


def test_build_dataset_rejects_too_short_time_series(reference_observations_factory):
    reference_observations_factory(hours=80)

    with pytest.raises(ValueError, match="Недостаточно наблюдений для построения датасета"):
        ModelLifecycleService().build_dataset(
            input_len_hours=72,
            forecast_horizon_hours=24,
        )


def test_split_by_time_keeps_non_empty_val_and_test_for_minimum_sample_count():
    dataset = {
        "X": [[[1.0]], [[2.0]], [[3.0]]],
        "y": [[[1.0]], [[2.0]], [[3.0]]],
        "input_start_ts": [1, 2, 3],
        "input_end_ts": [1, 2, 3],
        "target_start_ts": [1, 2, 3],
        "target_end_ts": [1, 2, 3],
        "feature_names": ["feature"],
        "target_names": ["target"],
    }

    split = split_by_time(
        dataset=dataset,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
    )

    assert len(split["X_train"]) == 1
    assert len(split["X_val"]) == 1
    assert len(split["X_test"]) == 1
