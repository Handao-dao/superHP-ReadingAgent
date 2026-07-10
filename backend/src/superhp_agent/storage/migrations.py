"""SQLite schema initialization and incremental upgrades.

This module owns table, index, and backward-compatible column creation. It does
not open connections, coordinate threads, or implement repository operations.
"""

from __future__ import annotations

import sqlite3

from superhp_agent.domain.vocabulary import normalize_pos, normalize_word


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the current local schema and upgrade older databases in place."""
    connection.executescript(
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
            profile_id TEXT NOT NULL DEFAULT 'english_novel',
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

        CREATE TABLE IF NOT EXISTS unit_progress (
            unit_id TEXT PRIMARY KEY,
            opened_at TEXT DEFAULT NULL,
            read_at TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL DEFAULT 'english_novel',
            normalized_word TEXT NOT NULL,
            word TEXT NOT NULL,
            translation TEXT NOT NULL,
            pos TEXT NOT NULL DEFAULT 'other',
            mastered INTEGER DEFAULT 0,
            mastered_at TEXT DEFAULT NULL,
            first_seen_at TEXT DEFAULT (datetime('now','localtime')),
            last_seen_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(profile_id, normalized_word)
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

        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id TEXT NOT NULL,
            chapter_id TEXT NOT NULL,
            body_kind TEXT NOT NULL,
            page_index INTEGER NOT NULL DEFAULT 0,
            progress_ratio REAL NOT NULL DEFAULT 0,
            total_pages INTEGER NOT NULL DEFAULT 0,
            label TEXT DEFAULT '',
            excerpt TEXT DEFAULT '',
            annotation_level TEXT DEFAULT '',
            paragraph_index INTEGER NOT NULL DEFAULT -1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_units_book_chapter_section
            ON units(book_id, chapter_no, section_no);
        CREATE INDEX IF NOT EXISTS idx_units_chapter_id ON units(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_vocab_mastered ON vocabulary(mastered);
        CREATE INDEX IF NOT EXISTS idx_unit_vocab_unit ON unit_vocabulary(unit_id);
        CREATE INDEX IF NOT EXISTS idx_unit_vocab_chapter ON unit_vocabulary(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_bookmarks_unit ON bookmarks(unit_id);
        """
    )
    _ensure_columns(connection)
    connection.commit()


def _ensure_columns(connection: sqlite3.Connection) -> None:
    """Apply small schema upgrades for existing local databases."""
    unit_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(units)").fetchall()
    }
    if "profile_id" not in unit_columns:
        connection.execute(
            "ALTER TABLE units ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'english_novel'"
        )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_units_profile ON units(profile_id)")

    vocabulary_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(vocabulary)").fetchall()
    }
    if not {"profile_id", "normalized_word"} <= vocabulary_columns:
        _migrate_vocabulary_scope(connection, vocabulary_columns)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_vocab_pos ON vocabulary(pos)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_vocab_profile ON vocabulary(profile_id)")

    bookmark_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(bookmarks)").fetchall()
    }
    if "annotation_level" not in bookmark_columns:
        connection.execute(
            "ALTER TABLE bookmarks ADD COLUMN annotation_level TEXT DEFAULT ''"
        )
    if "paragraph_index" not in bookmark_columns:
        connection.execute(
            "ALTER TABLE bookmarks ADD COLUMN paragraph_index INTEGER NOT NULL DEFAULT -1"
        )


def _migrate_vocabulary_scope(
    connection: sqlite3.Connection,
    old_columns: set[str],
) -> None:
    """Split legacy global words into profile-local vocabulary records."""
    old_rows = connection.execute("SELECT * FROM vocabulary ORDER BY id").fetchall()
    links = connection.execute(
        """
        SELECT uv.*, COALESCE(u.profile_id, 'english_novel') AS resolved_profile_id
        FROM unit_vocabulary uv
        LEFT JOIN units u ON u.id = uv.unit_id
        ORDER BY uv.unit_id, uv.vocab_id
        """
    ).fetchall()
    profiles_by_vocab: dict[int, set[str]] = {}
    for link in links:
        profiles_by_vocab.setdefault(int(link["vocab_id"]), set()).add(
            str(link["resolved_profile_id"] or "english_novel")
        )

    connection.executescript(
        """
        DROP TABLE IF EXISTS unit_vocabulary_scoped_new;
        DROP TABLE IF EXISTS vocabulary_scoped_new;
        CREATE TABLE vocabulary_scoped_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL DEFAULT 'english_novel',
            normalized_word TEXT NOT NULL,
            word TEXT NOT NULL,
            translation TEXT NOT NULL,
            pos TEXT NOT NULL DEFAULT 'other',
            mastered INTEGER DEFAULT 0,
            mastered_at TEXT DEFAULT NULL,
            first_seen_at TEXT DEFAULT (datetime('now','localtime')),
            last_seen_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(profile_id, normalized_word)
        );
        CREATE TABLE unit_vocabulary_scoped_new (
            unit_id TEXT NOT NULL,
            chapter_id TEXT NOT NULL,
            vocab_id INTEGER NOT NULL,
            translation TEXT NOT NULL,
            context TEXT DEFAULT '',
            encounter_count INTEGER DEFAULT 1,
            first_seen_at TEXT DEFAULT (datetime('now','localtime')),
            last_seen_at TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (unit_id, vocab_id),
            FOREIGN KEY (vocab_id) REFERENCES vocabulary_scoped_new(id) ON DELETE CASCADE
        );
        """
    )

    old_by_id = {int(row["id"]): row for row in old_rows}
    new_ids: dict[tuple[str, str], int] = {}
    for row in old_rows:
        old_id = int(row["id"])
        word = str(row["word"] or "").strip()
        normalized = normalize_word(word)
        if not normalized:
            continue
        fallback_profile = (
            str(row["profile_id"] or "english_novel")
            if "profile_id" in old_columns
            else "english_novel"
        )
        profiles = profiles_by_vocab.get(old_id) or {fallback_profile}
        for profile_id in sorted(profiles):
            key = (profile_id, normalized)
            connection.execute(
                """
                INSERT INTO vocabulary_scoped_new (
                    profile_id, normalized_word, word, translation, pos,
                    mastered, mastered_at, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id, normalized_word) DO UPDATE SET
                    mastered=MAX(vocabulary_scoped_new.mastered, excluded.mastered),
                    mastered_at=COALESCE(excluded.mastered_at, vocabulary_scoped_new.mastered_at),
                    last_seen_at=MAX(vocabulary_scoped_new.last_seen_at, excluded.last_seen_at)
                """,
                (
                    profile_id,
                    normalized,
                    word,
                    str(row["translation"] or ""),
                    normalize_pos(row["pos"] if "pos" in old_columns else "other"),
                    int(row["mastered"] or 0),
                    row["mastered_at"] if "mastered_at" in old_columns else None,
                    row["first_seen_at"] if "first_seen_at" in old_columns else None,
                    row["last_seen_at"] if "last_seen_at" in old_columns else None,
                ),
            )
            new_ids[key] = int(
                connection.execute(
                    """
                    SELECT id FROM vocabulary_scoped_new
                    WHERE profile_id = ? AND normalized_word = ?
                    """,
                    key,
                ).fetchone()["id"]
            )

    for link in links:
        old_row = old_by_id.get(int(link["vocab_id"]))
        if old_row is None:
            continue
        key = (
            str(link["resolved_profile_id"] or "english_novel"),
            normalize_word(old_row["word"]),
        )
        new_id = new_ids.get(key)
        if new_id is None:
            continue
        connection.execute(
            """
            INSERT INTO unit_vocabulary_scoped_new (
                unit_id, chapter_id, vocab_id, translation, context,
                encounter_count, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(unit_id, vocab_id) DO UPDATE SET
                translation=excluded.translation,
                context=excluded.context,
                encounter_count=(
                    unit_vocabulary_scoped_new.encounter_count + excluded.encounter_count
                ),
                last_seen_at=MAX(unit_vocabulary_scoped_new.last_seen_at, excluded.last_seen_at)
            """,
            (
                link["unit_id"],
                link["chapter_id"],
                new_id,
                link["translation"],
                link["context"],
                link["encounter_count"],
                link["first_seen_at"],
                link["last_seen_at"],
            ),
        )

    connection.executescript(
        """
        DROP TABLE unit_vocabulary;
        DROP TABLE vocabulary;
        ALTER TABLE vocabulary_scoped_new RENAME TO vocabulary;
        ALTER TABLE unit_vocabulary_scoped_new RENAME TO unit_vocabulary;
        CREATE INDEX idx_vocab_mastered ON vocabulary(mastered);
        CREATE INDEX idx_unit_vocab_unit ON unit_vocabulary(unit_id);
        CREATE INDEX idx_unit_vocab_chapter ON unit_vocabulary(chapter_id);
        """
    )
