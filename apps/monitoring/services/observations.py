import logging
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.monitoring.ingestion.types import Observation as IngestedObservation
from apps.monitoring.ingestion.utils import normalize_and_filter_observations
from apps.monitoring.models import Observation
from apps.monitoring.providers import MyCityAirCollector, OpenMeteoCollector, PlumeCollector
from apps.monitoring.providers.base import BaseCollector

from .utils import build_observation_fingerprint, parse_utc_datetime

logger = logging.getLogger(__name__)


@dataclass
class ObservationSourceReport:
    source: str
    status: str
    raw_count: int = 0
    error: str = ""


@dataclass
class ObservationSyncResult:
    raw_count: int
    cleaned_count: int
    db_created_count: int
    db_updated_count: int
    warnings: list[str]
    source_reports: list[ObservationSourceReport]


class ObservationSyncService:
    PLUME_PAGE_URL = "https://air.plumelabs.com/air-quality-in-Noril%27sk-6hwB"

    def _run_source_collectors(
        self,
        *,
        start: str,
        finish: str,
        interval: str,
        window_hours: int,
    ) -> tuple[list[IngestedObservation], list[ObservationSourceReport], list[str]]:
        collectors: list[tuple[str, BaseCollector, dict[str, Any]]] = [
            (
                "mycityair",
                MyCityAirCollector(window_hours=window_hours),
                {"start": start, "finish": finish, "interval": interval},
            ),
            (
                "open_meteo",
                OpenMeteoCollector(window_hours=window_hours),
                {"start": start, "finish": finish},
            ),
            (
                "plumelabs",
                PlumeCollector(page_url=self.PLUME_PAGE_URL, window_hours=window_hours),
                {"start": start, "finish": finish, "timeline": True},
            ),
        ]

        all_observations: list[IngestedObservation] = []
        reports: list[ObservationSourceReport] = []
        warnings: list[str] = []

        for source_key, collector, kwargs in collectors:
            try:
                source_observations = collector.collect(**kwargs)
            except Exception as exc:
                message = f"Источник {source_key} недоступен: {exc}"
                logger.warning("observation source failed source=%s error=%s", source_key, exc)
                reports.append(
                    ObservationSourceReport(
                        source=source_key,
                        status="failed",
                        raw_count=0,
                        error=str(exc),
                    )
                )
                warnings.append(message)
                continue

            raw_count = len(source_observations)
            reports.append(
                ObservationSourceReport(
                    source=source_key,
                    status="ok" if raw_count > 0 else "empty",
                    raw_count=raw_count,
                )
            )
            if raw_count == 0:
                warnings.append(f"Источник {source_key} вернул пустой ответ за выбранное окно.")

            all_observations.extend(source_observations)

        return all_observations, reports, warnings

    def collect(self, *, start: str, finish: str, interval: str, window_hours: int) -> ObservationSyncResult:
        logger.info(
            "observation collection started start=%s finish=%s interval=%s window_hours=%s",
            start,
            finish,
            interval,
            window_hours,
        )
        all_observations, source_reports, warnings = self._run_source_collectors(
            start=start,
            finish=finish,
            interval=interval,
            window_hours=window_hours,
        )

        if not all_observations:
            failed_sources = [report.source for report in source_reports if report.status == "failed"]
            if failed_sources:
                raise RuntimeError(f"Не удалось собрать данные: недоступны источники {', '.join(failed_sources)}")
            raise RuntimeError("Не удалось собрать данные: источники не вернули наблюдений за выбранное окно.")

        cleaned = normalize_and_filter_observations(
            all_observations,
            window_hours=window_hours,
        )
        created_count, updated_count = self.persist(cleaned)
        logger.info(
            "observation collection completed raw=%s cleaned=%s db_created=%s db_updated=%s warnings=%s",
            len(all_observations),
            len(cleaned),
            created_count,
            updated_count,
            len(warnings),
        )
        return ObservationSyncResult(
            raw_count=len(all_observations),
            cleaned_count=len(cleaned),
            db_created_count=created_count,
            db_updated_count=updated_count,
            warnings=warnings,
            source_reports=source_reports,
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
