import pytest

from apps.monitoring.models import Observation
from apps.monitoring.services.observations import ObservationSyncService

pytestmark = pytest.mark.django_db


def test_observation_persist_upserts_by_fingerprint(mycityair_observation_factory):
    service = ObservationSyncService()
    observation = mycityair_observation_factory()

    created_count, updated_count = service.persist([observation])
    assert created_count == 1
    assert updated_count == 0
    assert Observation.objects.count() == 1

    created_count, updated_count = service.persist([observation])
    assert created_count == 0
    assert updated_count == 1
    assert Observation.objects.count() == 1
