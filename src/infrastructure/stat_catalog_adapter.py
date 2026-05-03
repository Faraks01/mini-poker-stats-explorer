import json
from pathlib import Path
from typing import Optional

from src.domain.models import StatDefinition
from src.application.ports import StatCatalogPort


class JsonStatCatalogAdapter(StatCatalogPort):
    def __init__(self, path: str):
        self._path = Path(path)
        self._stats: list[StatDefinition] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"Каталог статистик не найден: {self._path}")

        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._stats = [StatDefinition.model_validate(item) for item in data]

    def get_all(self) -> list[StatDefinition]:
        return self._stats

    def get_by_id(self, stat_id: str) -> Optional[StatDefinition]:
        for stat in self._stats:
            if stat.id == stat_id:
                return stat
        return None

    def get_available(self) -> list[StatDefinition]:
        return [s for s in self._stats if s.state == "AVAILABLE"]
