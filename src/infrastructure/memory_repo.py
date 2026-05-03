from typing import Optional

from src.domain.models import Hand, FilterContext
from src.application.ports import HandRepository
from src.application.engines import FilterEngine


class InMemoryHandRepository(HandRepository):
    def __init__(self, filter_engine: FilterEngine):
        self._filter_engine = filter_engine
        self._hands: list[Hand] = []

    def add(self, hand: Hand) -> None:
        self._hands.append(hand)

    def add_many(self, hands: list[Hand]) -> None:
        self._hands.extend(hands)

    def clear(self) -> None:
        self._hands.clear()

    def get_all(self) -> list[Hand]:
        return self._hands

    def find_by_filter(self, context: FilterContext) -> list[Hand]:
        return self._filter_engine.apply(self._hands, context)

    def count(self) -> int:
        return len(self._hands)
