from abc import ABC, abstractmethod

from ..ingestion.types import Observation


class BaseCollector(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def collect(self, **kwargs) -> list[Observation]:
        raise NotImplementedError
