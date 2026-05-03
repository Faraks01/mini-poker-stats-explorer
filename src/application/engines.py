from abc import ABC, abstractmethod
from typing import Optional

from src.domain.hand_analysis import HandContext, PlayerContext
from src.domain.models import (
    Hand,
    StatDefinition,
    StatResult,
    FilterContext,
)


class FilterEngine(ABC):
    @abstractmethod
    def apply(self, hands: list[Hand], context: FilterContext) -> list[Hand]:
        pass

    @abstractmethod
    def matches(self, hand: Hand, context: FilterContext) -> bool:
        pass


class HandStatContextPort(ABC):
    """Контекст раздачи и матчинг стата (узкий порт для StatsEngine)."""

    @abstractmethod
    def analyze_hand(self, hand: Hand) -> HandContext:
        pass

    @abstractmethod
    def matches_stat(self, hand: Hand, stat: StatDefinition) -> bool:
        pass

    @abstractmethod
    def find_target_player(
        self, ctx: HandContext, stat: StatDefinition
    ) -> Optional[PlayerContext]:
        pass

    @abstractmethod
    def clear_cache(self) -> None:
        pass


class StatsEngine(ABC):
    @abstractmethod
    def calculate(
        self,
        hands: list[Hand],
        stat: StatDefinition,
    ) -> StatResult:
        pass

    @abstractmethod
    def calculate_opportunity(
        self,
        hands: list[Hand],
        stat: StatDefinition,
    ) -> int:
        pass

    @abstractmethod
    def calculate_success(
        self,
        hands: list[Hand],
        stat: StatDefinition,
    ) -> int:
        pass
