from abc import ABC, abstractmethod

from src.domain.models import Hand


class BaseHandHistoryParser(ABC):
    @abstractmethod
    def parse(self, content: str) -> list[Hand]:
        pass

    @abstractmethod
    def can_parse(self, content: str) -> bool:
        pass
