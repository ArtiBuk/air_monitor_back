from ninja import Schema


class MonitoringOverviewCountsSchema(Schema):
    observations: int
    datasets: int
    models: int
    forecasts: int
    experiments: int
    series: int
    scheduled_tasks: int


class AutomaticCollectionSchema(Schema):
    lookback_hours: int
    interval: str
    window_hours: int
    schedule_minute: int
    enabled_sources: list[str]


class MonitoringOverviewSchema(Schema):
    counts: MonitoringOverviewCountsSchema
    automatic_collection: AutomaticCollectionSchema
