"""
Кэш распарсенных рук в SQLite: ускорение повторного старта при неизменных файлах.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Optional

from src.domain.models import Hand


def _digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_fingerprint(path: Path) -> str:
    """Отпечаток содержимого источника: файл или каталог .txt."""
    path = path.resolve()
    if path.is_file():
        st = path.stat()
        payload = f"file|{path}|{st.st_size}|{int(st.st_mtime_ns)}"
        return _digest(payload)
    if path.is_dir():
        parts: list[str] = []
        for f in sorted(path.glob("*.txt")):
            try:
                st = f.stat()
                rel = f.name
                parts.append(f"{rel}|{st.st_size}|{int(st.st_mtime_ns)}")
            except OSError:
                parts.append(f"{f.name}|missing")
        payload = "dir|" + str(path) + "|" + "\n".join(parts)
        return _digest(payload)
    return _digest(f"missing|{path}")


def try_load_hands(
    db_path: str, source_name: str, fingerprint: str
) -> Optional[list[Hand]]:
    if not Path(db_path).is_file():
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT fingerprint, hand_count FROM hand_cache_meta WHERE source_name = ?",
            (source_name,),
        ).fetchone()
        if not row or row[0] != fingerprint:
            return None
        hand_count = int(row[1])
        if hand_count == 0:
            return []
        rows = conn.execute(
            "SELECT payload FROM hand_cache_rows WHERE source_name = ? ORDER BY ord",
            (source_name,),
        ).fetchall()
        if len(rows) != hand_count:
            return None
        hands: list[Hand] = []
        for (payload,) in rows:
            hands.append(Hand.model_validate_json(payload))
        return hands
    finally:
        conn.close()


def save_hands(
    db_path: str,
    source_name: str,
    resolved_path: str,
    fingerprint: str,
    hands: list[Hand],
) -> None:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hand_cache_meta (
                source_name TEXT NOT NULL PRIMARY KEY,
                source_path TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                hand_count INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hand_cache_rows (
                source_name TEXT NOT NULL,
                ord INTEGER NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (source_name, ord)
            )
            """
        )
        conn.execute("BEGIN")
        conn.execute("DELETE FROM hand_cache_meta WHERE source_name = ?", (source_name,))
        conn.execute("DELETE FROM hand_cache_rows WHERE source_name = ?", (source_name,))
        now = time.time()
        conn.execute(
            """
            INSERT INTO hand_cache_meta
            (source_name, source_path, fingerprint, hand_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_name, resolved_path, fingerprint, len(hands), now),
        )
        batch = [
            (source_name, i, h.model_dump_json())
            for i, h in enumerate(hands)
        ]
        conn.executemany(
            "INSERT INTO hand_cache_rows (source_name, ord, payload) VALUES (?, ?, ?)",
            batch,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
