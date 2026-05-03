from pathlib import Path
from typing import Protocol

from src.domain.models import Hand
from src.application.ports import HandHistoryLoader


class HandHistoryParser(Protocol):
    def parse(self, content: str) -> list[Hand]:
        ...


class FileHandHistoryLoader(HandHistoryLoader):
    def __init__(self, parser: HandHistoryParser):
        self._parser = parser

    def load(self, path: str) -> list[Hand]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Файл истории раздач не найден: {path}")

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        return self._parser.parse(content)

    def load_directory(self, directory: str) -> list[Hand]:
        dir_path = Path(directory)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Не каталог: {directory}")

        hands: list[Hand] = []
        for file_path in dir_path.glob("*.txt"):
            try:
                hands.extend(self.load(str(file_path)))
            except Exception:
                continue

        return hands
