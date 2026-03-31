from django.db import models


class ObservationQuerySet(models.QuerySet):
    def recent(self):
        return self.order_by("-observed_at_utc")

    def for_metric(self, metric: str):
        return self.filter(metric=metric)

    def from_source(self, source: str):
        return self.filter(source=source)

    def between(self, start=None, finish=None):
        queryset = self
        if start is not None:
            queryset = queryset.filter(observed_at_utc__gte=start)
        if finish is not None:
            queryset = queryset.filter(observed_at_utc__lte=finish)
        return queryset


class ForecastRunQuerySet(models.QuerySet):
    def successful(self):
        return self.filter(status="success")
