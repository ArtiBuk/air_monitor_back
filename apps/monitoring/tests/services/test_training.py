import pytest

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
