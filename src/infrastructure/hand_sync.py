"""
Синхронизация данных из DataLoader в InMemoryHandRepository.
DataLoader не знает о репозиториях; вызов выполняет точка входа (API / use case).
"""

from src.infrastructure.data_loader import DataLoader
from src.infrastructure.memory_repo import InMemoryHandRepository


def sync_repository_from_loader(
    loader: DataLoader,
    source: str,
    repository: InMemoryHandRepository,
) -> None:
    hands = loader.get_hands(source)
    repository.clear()
    if hands:
        repository.add_many(hands)
