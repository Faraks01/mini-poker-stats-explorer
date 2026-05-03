from src.domain.models import Hand
from src.infrastructure.parsers.base import BaseHandHistoryParser
from src.infrastructure.parsers.pokerstars import PokerStarsParser
from src.infrastructure.parsers.wpn import WPNParser


class CompositeParser(BaseHandHistoryParser):
    """Парсер с автоопределением формата; делегирует специализированным парсерам."""

    def __init__(self):
        self._parsers: list[BaseHandHistoryParser] = [
            PokerStarsParser(),
            WPNParser(),
        ]

    def can_parse(self, content: str) -> bool:
        return any(p.can_parse(content) for p in self._parsers)

    def parse(self, content: str) -> list[Hand]:
        for parser in self._parsers:
            if parser.can_parse(content):
                return parser.parse(content)
        return []

    def add_parser(self, parser: BaseHandHistoryParser) -> None:
        self._parsers.insert(0, parser)
