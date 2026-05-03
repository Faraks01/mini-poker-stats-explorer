from abc import ABC, abstractmethod
from typing import Optional

from src.domain.models import Hand, StatDefinition, FilterContext


class HandRepository(ABC):
    @abstractmethod
    def get_all(self) -> list[Hand]:
        pass

    @abstractmethod
    def find_by_filter(self, context: FilterContext) -> list[Hand]:
        pass

    @abstractmethod
    def count(self) -> int:
        pass


class StatCatalogPort(ABC):
    @abstractmethod
    def get_all(self) -> list[StatDefinition]:
        pass

    @abstractmethod
    def get_by_id(self, stat_id: str) -> Optional[StatDefinition]:
        pass

    @abstractmethod
    def get_available(self) -> list[StatDefinition]:
        pass


class HandHistoryLoader(ABC):
    @abstractmethod
    def load(self, path: str) -> list[Hand]:
        pass

    @abstractmethod
    def load_directory(self, directory: str) -> list[Hand]:
        pass
