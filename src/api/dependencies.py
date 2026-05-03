"""
Внедрение зависимостей FastAPI.
"""

from functools import lru_cache
from pathlib import Path

from src.application.ports import StatCatalogPort
from src.infrastructure.stat_catalog_adapter import JsonStatCatalogAdapter
from src.infrastructure.filter_engine import DefaultFilterEngine
from src.infrastructure.stats_engine import DefaultStatsEngine
from src.infrastructure.data_loader import DataLoader, get_data_loader
from src.infrastructure.memory_repo import InMemoryHandRepository


GTO_SOURCE = "gto"
POPULATION_SOURCE = "population"


@lru_cache()
def get_catalog() -> StatCatalogPort:
    catalog_path = Path(__file__).parent.parent.parent / "stat_catalog.json"
    return JsonStatCatalogAdapter(str(catalog_path))


@lru_cache()
def get_filter_engine() -> DefaultFilterEngine:
    return DefaultFilterEngine()


@lru_cache()
def get_stats_engine() -> DefaultStatsEngine:
    fe = get_filter_engine()
    return DefaultStatsEngine(fe)


@lru_cache()
def get_gto_repository() -> InMemoryHandRepository:
    return InMemoryHandRepository(get_filter_engine())


@lru_cache()
def get_population_repository() -> InMemoryHandRepository:
    return InMemoryHandRepository(get_filter_engine())


def get_hand_repository(source: str) -> InMemoryHandRepository:
    if source == GTO_SOURCE:
        return get_gto_repository()
    if source == POPULATION_SOURCE:
        return get_population_repository()
    raise ValueError(f"Неизвестный источник: {source}")


def get_loader() -> DataLoader:
    return get_data_loader()


def init_data_sources(loader: DataLoader, base_path: str) -> None:
    gto_path = Path(base_path) / "GTO bots data"
    pop_path = Path(base_path) / "Тестовая база данные популяции"

    if gto_path.exists():
        loader.register_source(GTO_SOURCE, str(gto_path))

    if pop_path.exists():
        loader.register_source(POPULATION_SOURCE, str(pop_path))
