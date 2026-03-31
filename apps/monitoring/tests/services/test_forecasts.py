import pytest

from apps.monitoring.services.evaluation import ForecastEvaluationService
from apps.monitoring.services.forecasts import ForecastService

pytestmark = pytest.mark.django_db


def test_forecast_service_requires_active_model():
    with pytest.raises(ValueError, match="No active trained model found in database."):
        ForecastService().generate()


def test_forecast_service_rejects_horizon_mismatch(model_version_factory):
    model_version = model_version_factory(forecast_horizon_hours=24, input_len_hours=72)

    with pytest.raises(ValueError, match="Requested forecast horizon does not match trained model horizon"):
        ForecastService().generate(model_version=model_version, forecast_horizon_hours=12)


def test_forecast_service_rejects_input_window_mismatch(model_version_factory):
    model_version = model_version_factory(forecast_horizon_hours=24, input_len_hours=72)

    with pytest.raises(ValueError, match="Requested input window does not match trained model input window"):
        ForecastService().generate(model_version=model_version, input_len_hours=48)


def test_forecast_evaluation_requires_successful_run():
    class DummyForecastRun:
        status = "failed"
        model_version_id = None

    with pytest.raises(ValueError, match="Only successful forecast runs can be evaluated."):
        ForecastEvaluationService().evaluate(forecast_run=DummyForecastRun())
