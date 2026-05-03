"""
Ленивая загрузка историй раздач с кэшированием.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable

from src.domain.models import Hand
from src.infrastructure.parsers.composite import CompositeParser
from src.infrastructure.file_loader import FileHandHistoryLoader
from src.infrastructure.hand_sqlite_cache import (
    compute_fingerprint,
    try_load_hands,
    save_hands,
)


class LoadingState(str, Enum):
    NOT_STARTED = "not_started"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"


def _load_one_file(path: str) -> list[Hand]:
    """Отдельный парсер на вызов — безопасно для пула потоков."""
    loader = FileHandHistoryLoader(CompositeParser())
    return loader.load(path)


def _cache_rebuild_requested() -> bool:
    v = os.environ.get("STATS_SQLITE_CACHE_REBUILD", "").lower()
    return v in ("1", "true", "yes")


@dataclass
class DataSource:
    name: str
    path: str
    state: LoadingState = LoadingState.NOT_STARTED
    hands: list[Hand] = field(default_factory=list)
    error: Optional[str] = None
    files_loaded: int = 0
    files_total: int = 0


class DataLoader:
    def __init__(
        self,
        sqlite_cache_path: Optional[str] = None,
        load_workers: Optional[int] = None,
    ):
        self._sqlite_cache_path = sqlite_cache_path
        cpu = os.cpu_count() or 4
        default_workers = max(1, min(8, cpu + 2))
        self._load_workers = (
            load_workers if load_workers is not None else default_workers
        )
        self._sources: dict[str, DataSource] = {}
        self._lock = threading.Lock()
        self._loading_threads: dict[str, threading.Thread] = {}

    def register_source(self, name: str, path: str) -> None:
        with self._lock:
            self._sources[name] = DataSource(name=name, path=path)

    def get_state(self, name: str) -> Optional[LoadingState]:
        source = self._sources.get(name)
        return source.state if source else None

    def get_progress(self, name: str) -> tuple[int, int]:
        source = self._sources.get(name)
        if not source:
            return 0, 0
        return source.files_loaded, source.files_total

    def get_hands(self, name: str) -> list[Hand]:
        source = self._sources.get(name)
        if not source:
            return []

        if source.state == LoadingState.NOT_STARTED:
            self._load_sync(name)

        return source.hands

    def get_hands_if_loaded(self, name: str) -> Optional[list[Hand]]:
        source = self._sources.get(name)
        if not source or source.state != LoadingState.LOADED:
            return None
        return source.hands

    def start_loading(self, name: str, callback: Optional[Callable] = None) -> bool:
        source = self._sources.get(name)
        if not source:
            return False

        if source.state in (LoadingState.LOADING, LoadingState.LOADED):
            return False

        thread = threading.Thread(
            target=self._load_async,
            args=(name, callback),
            daemon=True,
        )
        self._loading_threads[name] = thread
        thread.start()
        return True

    def _load_sync(self, name: str) -> None:
        source = self._sources.get(name)
        if not source:
            return

        with self._lock:
            if source.state != LoadingState.NOT_STARTED:
                return
            source.state = LoadingState.LOADING

        try:
            self._do_load(source)
            source.state = LoadingState.LOADED
        except Exception as e:
            source.state = LoadingState.ERROR
            source.error = str(e)

    def _load_async(self, name: str, callback: Optional[Callable]) -> None:
        source = self._sources.get(name)
        if not source:
            return

        with self._lock:
            source.state = LoadingState.LOADING

        try:
            self._do_load(source)
            source.state = LoadingState.LOADED
        except Exception as e:
            source.state = LoadingState.ERROR
            source.error = str(e)

        if callback:
            callback(name, source.state)

    def _try_cache(self, source: DataSource, path: Path, fingerprint: str) -> bool:
        if not self._sqlite_cache_path or _cache_rebuild_requested():
            return False
        cached = try_load_hands(self._sqlite_cache_path, source.name, fingerprint)
        if cached is None:
            return False
        source.hands = cached
        if path.is_file():
            source.files_total = 1
            source.files_loaded = 1
        elif path.is_dir():
            source.files_total = len(list(path.glob("*.txt")))
            source.files_loaded = source.files_total
        return True

    def _load_dir_parallel(self, source: DataSource, files: list[Path]) -> None:
        source.files_total = len(files)
        if not files:
            source.hands = []
            source.files_loaded = 0
            return

        by_path: dict[str, list[Hand]] = {}
        workers = min(self._load_workers, len(files))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(_load_one_file, str(p)): p for p in files}
            done = 0
            for fut in as_completed(future_map):
                p = future_map[fut]
                try:
                    by_path[str(p)] = fut.result()
                except Exception:
                    by_path[str(p)] = []
                done += 1
                source.files_loaded = done

        ordered = [by_path[str(p)] for p in files]
        merged: list[Hand] = []
        for chunk in ordered:
            merged.extend(chunk)
        source.hands = merged

    def _do_load(self, source: DataSource) -> None:
        path = Path(source.path)
        fingerprint = compute_fingerprint(path)

        if self._try_cache(source, path, fingerprint):
            return

        if path.is_file():
            source.files_total = 1
            source.hands = _load_one_file(str(path))
            source.files_loaded = 1
        elif path.is_dir():
            files = sorted(path.glob("*.txt"), key=lambda p: p.name)
            self._load_dir_parallel(source, files)
        else:
            raise FileNotFoundError(f"Путь не найден: {source.path}")

        if self._sqlite_cache_path:
            save_hands(
                self._sqlite_cache_path,
                source.name,
                str(path.resolve()),
                fingerprint,
                source.hands,
            )

    def get_all_sources_status(self) -> dict[str, dict]:
        result = {}
        for name, source in self._sources.items():
            result[name] = {
                "state": source.state.value,
                "hands_count": len(source.hands),
                "files_loaded": source.files_loaded,
                "files_total": source.files_total,
                "error": source.error,
            }
        return result


_data_loader: Optional[DataLoader] = None

# Каталог проекта (…/mini-poker-stats-explorer)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STATS_SQLITE_CACHE = str(_PROJECT_ROOT / ".cache" / "hands.db")
DEFAULT_STATS_LOAD_WORKERS = max(1, min(8, (os.cpu_count() or 4) + 2))


def _sqlite_cache_path_from_env() -> Optional[str]:
    """
    По умолчанию: .cache/hands.db в корне проекта.
    Отключить кэш: STATS_SQLITE_CACHE= (пустая строка).
    Относительные пути в .env считаются от корня репозитория.
    """
    if "STATS_SQLITE_CACHE" in os.environ:
        raw = os.environ["STATS_SQLITE_CACHE"].strip()
        if raw == "":
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return str(p)
    return DEFAULT_STATS_SQLITE_CACHE


def _load_workers_from_env() -> int:
    raw = os.environ.get("STATS_LOAD_WORKERS", "").strip()
    if not raw:
        return DEFAULT_STATS_LOAD_WORKERS
    return max(1, int(raw))


def get_data_loader() -> DataLoader:
    global _data_loader
    if _data_loader is None:
        _data_loader = DataLoader(
            sqlite_cache_path=_sqlite_cache_path_from_env(),
            load_workers=_load_workers_from_env(),
        )
    return _data_loader
