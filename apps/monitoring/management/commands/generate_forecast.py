from django.core.management.base import BaseCommand

from apps.monitoring.services.forecasts import ForecastService


class Command(BaseCommand):
    help = "Generate and store the next forecast window."

    def add_arguments(self, parser):
        parser.add_argument("--input-len-hours", type=int, default=None)
        parser.add_argument("--forecast-horizon-hours", type=int, default=None)

    def handle(self, *args, **options):
        result = ForecastService().generate(
            input_len_hours=options["input_len_hours"],
            forecast_horizon_hours=options["forecast_horizon_hours"],
        )
        self.stdout.write(
            str(
                {
                    "run_id": result.run_id,
                    "generated_from_timestamp_utc": result.generated_from_timestamp_utc,
                    "forecast_horizon_hours": result.forecast_horizon_hours,
                    "record_count": len(result.records),
                }
            )
        )
