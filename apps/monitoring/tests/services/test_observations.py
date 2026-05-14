from unittest.mock import patch

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


@patch("apps.monitoring.services.observations.OpenMeteoCollector.collect")
@patch("apps.monitoring.services.observations.PlumeCollector.collect")
@patch("apps.monitoring.services.observations.MyCityAirCollector.collect")
def test_collect_keeps_partial_success_and_returns_warning(
    mycityair_collect,
    plume_collect,
    open_meteo_collect,
    mycityair_observation_factory,
):
    mycityair_collect.return_value = [mycityair_observation_factory()]
    plume_collect.side_effect = RuntimeError("502 Server Error: Bad Gateway")
    open_meteo_collect.return_value = [
        mycityair_observation_factory(
            source="open_meteo",
            source_kind="open_meteo_api",
            station_id=None,
            station_name="Норильск (городской фон)",
            metric="pm25",
            unit="µg/m3",
            extra={"provider": "open_meteo"},
        )
    ]

    result = ObservationSyncService().collect(
        start="2026-04-08T00:00:00Z",
        finish="2026-04-08T03:00:00Z",
        interval="Interval1H",
        window_hours=1,
    )

    assert result.raw_count == 2
    assert result.cleaned_count == 2
    assert result.db_created_count == 2
    assert result.db_updated_count == 0
    assert len(result.warnings) == 1
    assert "plumelabs" in result.warnings[0]
    assert {report.source: report.status for report in result.source_reports} == {
        "mycityair": "ok",
        "open_meteo": "ok",
        "plumelabs": "failed",
    }


@patch("apps.monitoring.services.observations.OpenMeteoCollector.collect")
@patch("apps.monitoring.services.observations.PlumeCollector.collect")
@patch("apps.monitoring.services.observations.MyCityAirCollector.collect")
def test_collect_raises_if_all_sources_fail(mycityair_collect, plume_collect, open_meteo_collect):
    mycityair_collect.side_effect = RuntimeError("token invalid")
    plume_collect.side_effect = RuntimeError("upstream timeout")
    open_meteo_collect.side_effect = RuntimeError("upstream timeout")

    with pytest.raises(RuntimeError, match="недоступны источники"):
        ObservationSyncService().collect(
            start="2026-04-08T00:00:00Z",
            finish="2026-04-08T03:00:00Z",
            interval="Interval1H",
            window_hours=1,
        )
