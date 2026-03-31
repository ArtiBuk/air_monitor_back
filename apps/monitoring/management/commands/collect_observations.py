from dataclasses import asdict
from datetime import UTC, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.monitoring.services.observations import ObservationSyncService


class Command(BaseCommand):
    help = "Collect observations from configured sources and persist them in files and DB."

    def add_arguments(self, parser):
        parser.add_argument("--start", default="")
        parser.add_argument("--finish", default="")
        parser.add_argument("--interval", default=settings.MONITORING_INTERVAL)
        parser.add_argument("--window-hours", type=int, default=settings.MONITORING_WINDOW_HOURS)

    def handle(self, *args, **options):
        finish = options["finish"] or timezone.now().astimezone(UTC).isoformat().replace("+00:00", "Z")
        start = options["start"] or (
            timezone.now().astimezone(UTC) - timedelta(hours=settings.MONITORING_COLLECTION_LOOKBACK_HOURS)
        ).isoformat().replace("+00:00", "Z")

        result = ObservationSyncService().collect(
            start=start,
            finish=finish,
            interval=options["interval"],
            window_hours=options["window_hours"],
        )
        self.stdout.write(str(asdict(result)))
