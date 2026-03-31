import json

import pytest

from .factories import (
    build_monitoring_auth_payload,
    build_mycityair_observation,
    build_plume_observation,
    create_dataset_snapshot,
    create_experiment_run,
    create_experiment_series,
    create_forecast_evaluation,
    create_forecast_run,
    create_model_version,
    create_reference_observations,
)


@pytest.fixture
def json_post(client):
    def sender(path: str, payload: dict):
        return client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    return sender


@pytest.fixture
def authenticated_client(client):
    response = client.post(
        "/api/auth/register",
        data=json.dumps(build_monitoring_auth_payload()),
        content_type="application/json",
    )
    assert response.status_code == 201
    return client


@pytest.fixture
def mycityair_observation_factory():
    return build_mycityair_observation


@pytest.fixture
def plume_observation_factory():
    return build_plume_observation


@pytest.fixture
def dataset_snapshot_factory(db):
    return create_dataset_snapshot


@pytest.fixture
def model_version_factory(db):
    return create_model_version


@pytest.fixture
def experiment_series_factory(db):
    return create_experiment_series


@pytest.fixture
def experiment_run_factory(db):
    return create_experiment_run


@pytest.fixture
def forecast_run_factory(db):
    return create_forecast_run


@pytest.fixture
def forecast_evaluation_factory(db):
    return create_forecast_evaluation


@pytest.fixture
def reference_observations_factory(db):
    return create_reference_observations
