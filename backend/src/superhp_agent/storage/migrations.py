"""SQLite schema initialization and incremental upgrades.

This module owns table, index, and backward-compatible column creation. It does
not open connections, coordinate threads, or implement repository operations.
"""

from __future__ import annotations

import sqlite3


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
            word TEXT NOT NULL UNIQUE,
            translation TEXT NOT NULL,
            pos TEXT NOT NULL DEFAULT 'other',
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
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(vocabulary)").fetchall()
    }
    if "pos" not in columns:
        connection.execute("ALTER TABLE vocabulary ADD COLUMN pos TEXT NOT NULL DEFAULT 'other'")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_vocab_pos ON vocabulary(pos)")

    unit_columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(units)").fetchall()
    }
    if "profile_id" not in unit_columns:
        connection.execute(
            "ALTER TABLE units ADD COLUMN profile_id TEXT NOT NULL DEFAULT 'english_novel'"
        )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_units_profile ON units(profile_id)")
