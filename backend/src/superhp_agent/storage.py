"""SQLite storage for reading units, progress, and vocabulary.

The JSON memory file is enough for simple flow decisions, but vocabulary needs a
queryable store for review screens and cross-unit aggregation. AppDB owns that
relational side of the local backend state.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from superhp_agent.corpus import ReadingUnit

ANNOTATION_MARKER_RE = re.compile(r"\[\[(.+?)\|.+?\]\]")


def strip_annotation_markers(text: str) -> str:
    """Return source text with inline annotation markers removed."""
    return ANNOTATION_MARKER_RE.sub(r"\1", text)


class AppDB:
    """Thin SQLite gateway used by services and API endpoints."""
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # FastAPI and WebSocket handlers can interleave on the same process, so
        # serialize access around the shared sqlite connection.
        self._lock = threading.RLock()
        self._init_tables()

    def close(self) -> None:
        self._conn.close()

    def sync_unit(self, unit: ReadingUnit) -> None:
        """Upsert corpus metadata so vocabulary rows can reference a unit."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO units (
                    id, chapter_id, book_id, book_title, chapter_no, chapter_title,
                    section_no, section_count, summary, source_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    chapter_id=excluded.chapter_id,
                    book_id=excluded.book_id,
                    book_title=excluded.book_title,
                    chapter_no=excluded.chapter_no,
                    chapter_title=excluded.chapter_title,
                    section_no=excluded.section_no,
                    section_count=excluded.section_count,
                    summary=excluded.summary,
                    source_path=excluded.source_path
                """,
                (
                    unit.id,
                    unit.chapter_id,
                    unit.book_id,
                    unit.book_title,
                    unit.chapter_no,
                    unit.chapter_title,
                    unit.section_no,
                    unit.section_count,
                    unit.summary,
                    str(unit.path),
                ),
            )
            self._conn.commit()

    def add_vocabulary_items(self, unit: ReadingUnit, items: list[Any]) -> int:
        """Store extracted vocabulary and its unit-specific encounter context."""
        inserted = 0
        with self._lock:
            self.sync_unit(unit)
            for item in items:
                word = str(getattr(item, "word", "") or "").strip()
                translation = str(getattr(item, "translation", "") or "").strip()
                context = strip_annotation_markers(str(getattr(item, "context", "") or "")).strip()
                if not word or not translation:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO vocabulary (word, translation)
                    VALUES (?, ?)
                    ON CONFLICT(word) DO UPDATE SET
                        translation=excluded.translation,
                        last_seen_at=datetime('now','localtime')
                    """,
                    (word, translation),
                )
                vocab_id = self._conn.execute(
                    "SELECT id FROM vocabulary WHERE word = ?",
                    (word,),
                ).fetchone()["id"]
                self._conn.execute(
                    """
                    INSERT INTO unit_vocabulary (unit_id, chapter_id, vocab_id, translation, context)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(unit_id, vocab_id) DO UPDATE SET
                        translation=excluded.translation,
                        context=excluded.context,
                        encounter_count=unit_vocabulary.encounter_count + 1,
                        last_seen_at=datetime('now','localtime')
                    """,
                    (unit.id, unit.chapter_id, vocab_id, translation, context),
                )
                inserted += 1
            self._conn.commit()
        return inserted

    def add_manual_vocabulary(
        self,
        unit: ReadingUnit,
        *,
        word: str,
        translation: str,
        context: str = "",
    ) -> int:
        """Store one user-selected lookup result and return its vocabulary id."""
        word = word.strip()
        translation = translation.strip()
        context = strip_annotation_markers(context).strip()
        if not word or not translation:
            raise ValueError("word and translation are required")

        with self._lock:
            self.sync_unit(unit)
            self._conn.execute(
                """
                INSERT INTO vocabulary (word, translation, mastered, mastered_at)
                VALUES (?, ?, 0, NULL)
                ON CONFLICT(word) DO UPDATE SET
                    translation=excluded.translation,
                    mastered=0,
                    mastered_at=NULL,
                    last_seen_at=datetime('now','localtime')
                """,
                (word, translation),
            )
            vocab_id = int(
                self._conn.execute(
                    "SELECT id FROM vocabulary WHERE word = ?",
                    (word,),
                ).fetchone()["id"]
            )
            self._conn.execute(
                """
                INSERT INTO unit_vocabulary (unit_id, chapter_id, vocab_id, translation, context)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(unit_id, vocab_id) DO UPDATE SET
                    translation=excluded.translation,
                    context=excluded.context,
                    last_seen_at=datetime('now','localtime')
                """,
                (unit.id, unit.chapter_id, vocab_id, translation, context),
            )
            self._conn.commit()
            return vocab_id

    def set_mastered(self, vocab_id: int, mastered: bool) -> bool:
        """Mark one vocabulary item mastered or active."""
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE vocabulary
                SET mastered = ?,
                    mastered_at = CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END,
                    last_seen_at = datetime('now','localtime')
                WHERE id = ?
                """,
                (1 if mastered else 0, 1 if mastered else 0, vocab_id),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def set_mastered_by_word(self, word: str, mastered: bool) -> bool:
        """Mark vocabulary by word, used by inline reading actions."""
        normalized = word.strip().lower()
        if not normalized:
            return False
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE vocabulary
                SET mastered = ?,
                    mastered_at = CASE WHEN ? THEN datetime('now','localtime') ELSE NULL END,
                    last_seen_at = datetime('now','localtime')
                WHERE lower(word) = ?
                """,
                (1 if mastered else 0, 1 if mastered else 0, normalized),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_vocabulary(self, vocab_id: int) -> bool:
        """Remove a vocabulary item and its unit links."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM vocabulary WHERE id = ?", (vocab_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def count_vocabulary_for_unit(self, unit_id: str) -> int:
        """Return the number shown on guided cards for one reading unit."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM unit_vocabulary uv
                JOIN vocabulary v ON v.id = uv.vocab_id
                WHERE uv.unit_id = ? AND v.mastered = 0
                """,
                (unit_id,),
            ).fetchone()
            return int(row["count"] if row else 0)

    def list_vocabulary(
        self,
        *,
        unit_id: str | None = None,
        chapter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if unit_id:
            clauses.append("uv.unit_id = ?")
            params.append(unit_id)
        if chapter_id:
            clauses.append("uv.chapter_id = ?")
            params.append(chapter_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT
                v.id,
                v.word,
                v.translation AS global_translation,
                v.mastered,
                uv.translation,
                uv.context,
                uv.encounter_count,
                uv.unit_id,
                uv.chapter_id,
                uv.first_seen_at,
                uv.last_seen_at
            FROM unit_vocabulary uv
            JOIN vocabulary v ON v.id = uv.vocab_id
            {where}
            ORDER BY uv.last_seen_at DESC, lower(v.word)
        """
        with self._lock:
            return [dict(row) for row in self._conn.execute(query, params).fetchall()]

    def _init_tables(self) -> None:
        """Create the local schema lazily so first run needs no setup command."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS units (
                id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                book_title TEXT NOT NULL,
                chapter_no INTEGER NOT NULL,
                chapter_title TEXT NOT NULL,
                section_no INTEGER NOT NULL DEFAULT 1,
                section_count INTEGER NOT NULL DEFAULT 1,
                summary TEXT DEFAULT '',
                source_path TEXT NOT NULL,
                annotated_path TEXT DEFAULT '',
                status TEXT DEFAULT 'unread',
                annotated_at TEXT DEFAULT NULL,
                read_at TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS reading_progress (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_unit_id TEXT DEFAULT '',
                last_opened_at TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE,
                translation TEXT NOT NULL,
                mastered INTEGER DEFAULT 0,
                mastered_at TEXT DEFAULT NULL,
                first_seen_at TEXT DEFAULT (datetime('now','localtime')),
                last_seen_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS unit_vocabulary (
                unit_id TEXT NOT NULL,
                chapter_id TEXT NOT NULL,
                vocab_id INTEGER NOT NULL,
                translation TEXT NOT NULL,
                context TEXT DEFAULT '',
                encounter_count INTEGER DEFAULT 1,
                first_seen_at TEXT DEFAULT (datetime('now','localtime')),
                last_seen_at TEXT DEFAULT (datetime('now','localtime')),
                PRIMARY KEY (unit_id, vocab_id),
                FOREIGN KEY (vocab_id) REFERENCES vocabulary(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_units_book_chapter_section
                ON units(book_id, chapter_no, section_no);
            CREATE INDEX IF NOT EXISTS idx_units_chapter_id ON units(chapter_id);
            CREATE INDEX IF NOT EXISTS idx_vocab_mastered ON vocabulary(mastered);
            CREATE INDEX IF NOT EXISTS idx_unit_vocab_unit ON unit_vocabulary(unit_id);
            CREATE INDEX IF NOT EXISTS idx_unit_vocab_chapter ON unit_vocabulary(chapter_id);
            """
        )
        self._conn.commit()
