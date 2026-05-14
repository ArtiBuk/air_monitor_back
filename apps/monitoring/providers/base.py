from abc import ABC, abstractmethod
from typing import Any

from ..ingestion.types import Observation


class BaseCollector(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def collect(self, **kwargs: Any) -> list[Observation]:
        raise NotImplementedError
