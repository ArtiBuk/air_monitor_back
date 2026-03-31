import logging
from dataclasses import dataclass

from django.db import transaction

from apps.monitoring.ingestion.utils import normalize_and_filter_observations
from apps.monitoring.models import Observation
from apps.monitoring.providers import MyCityAirCollector, PlumeCollector

from .utils import build_observation_fingerprint, parse_utc_datetime

logger = logging.getLogger(__name__)


@dataclass
class ObservationSyncResult:
    raw_count: int
    cleaned_count: int
    db_created_count: int
    db_updated_count: int


class ObservationSyncService:
    def collect(self, *, start: str, finish: str, interval: str, window_hours: int) -> ObservationSyncResult:
        logger.info(
            "observation collection started start=%s finish=%s interval=%s window_hours=%s",
            start,
            finish,
            interval,
            window_hours,
        )
        all_observations = []

        mycityair = MyCityAirCollector(window_hours=window_hours)
        all_observations.extend(mycityair.collect(start=start, finish=finish, interval=interval))

        plume = PlumeCollector("https://air.plumelabs.com/air-quality-in-Noril%27sk-6hwB", window_hours=window_hours)
        all_observations.extend(plume.collect(start=start, finish=finish, timeline=True))

        cleaned = normalize_and_filter_observations(
            all_observations,
            window_hours=window_hours,
        )
        created_count, updated_count = self.persist(cleaned)
        logger.info(
            "observation collection completed raw=%s cleaned=%s db_created=%s db_updated=%s",
            len(all_observations),
            len(cleaned),
            created_count,
            updated_count,
        )
        return ObservationSyncResult(
            raw_count=len(all_observations),
            cleaned_count=len(cleaned),
            db_created_count=created_count,
            db_updated_count=updated_count,
        )

    @transaction.atomic
    def persist(self, observations) -> tuple[int, int]:
        created_count = 0
        updated_count = 0

        for item in observations:
            dedup_key = (
                item.source,
                item.station_id or "",
                item.station_name or "",
                item.lat,
                item.lon,
                item.observed_at_utc,
                item.time_bucket_utc,
                item.time_window_utc,
                item.metric,
                item.value,
                item.unit,
            )
            fingerprint = build_observation_fingerprint(dedup_key)
            _, created = Observation.objects.update_or_create(
                fingerprint=fingerprint,
                defaults={
                    "source": item.source,
                    "source_kind": item.source_kind or "",
                    "station_id": item.station_id or "",
                    "station_name": item.station_name or "",
                    "lat": item.lat,
                    "lon": item.lon,
                    "observed_at_utc": parse_utc_datetime(item.observed_at_utc),
                    "time_bucket_utc": parse_utc_datetime(item.time_bucket_utc),
                    "time_window_utc": parse_utc_datetime(item.time_window_utc),
                    "metric": item.metric,
                    "value": item.value,
                    "unit": item.unit or "",
                    "extra": item.extra or {},
                },
            )
            created_count += int(created)
            updated_count += int(not created)

        logger.info(
            "observation persistence completed processed=%s created=%s updated=%s",
            len(observations),
            created_count,
            updated_count,
        )
        return created_count, updated_count
