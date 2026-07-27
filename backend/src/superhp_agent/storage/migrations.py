"""Create the current SQLite schema for disposable local application data.

The project intentionally resets pre-redesign test data instead of migrating
the former profile-scoped vocabulary table. Future schema changes can add
versioned migrations once user-owned production data exists.
"""

from __future__ import annotations

import sqlite3


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the current storage schema on a new or already-current database."""
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
            profile_id TEXT NOT NULL,
            language_id TEXT NOT NULL,
            source_path TEXT NOT NULL
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

        CREATE TABLE IF NOT EXISTS lexemes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            language_id TEXT NOT NULL,
            normalized_word TEXT NOT NULL,
            display_word TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(language_id, normalized_word)
        );

        CREATE TABLE IF NOT EXISTS lexeme_mastery (
            lexeme_id INTEGER PRIMARY KEY,
            mastered INTEGER NOT NULL DEFAULT 0,
            mastered_at TEXT DEFAULT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (lexeme_id) REFERENCES lexemes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS book_vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            lexeme_id INTEGER NOT NULL,
            translation TEXT NOT NULL,
            pos TEXT NOT NULL DEFAULT 'other',
            first_seen_at TEXT DEFAULT (datetime('now','localtime')),
            last_seen_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(book_id, lexeme_id),
            FOREIGN KEY (lexeme_id) REFERENCES lexemes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS unit_vocabulary (
            unit_id TEXT NOT NULL,
            chapter_id TEXT NOT NULL,
            book_vocab_id INTEGER NOT NULL,
            translation TEXT NOT NULL,
            context TEXT DEFAULT '',
            encounter_count INTEGER DEFAULT 1,
            first_seen_at TEXT DEFAULT (datetime('now','localtime')),
            last_seen_at TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (unit_id, book_vocab_id),
            FOREIGN KEY (book_vocab_id) REFERENCES book_vocabulary(id) ON DELETE CASCADE
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
            paragraph_index INTEGER NOT NULL DEFAULT -1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS recommendation_catalog (
            id TEXT PRIMARY KEY,
            title_en TEXT NOT NULL,
            title_zh TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            entry_kind TEXT NOT NULL DEFAULT 'unknown'
                CHECK (entry_kind IN ('book', 'series', 'collection', 'unknown')),
            lexile_min INTEGER NOT NULL,
            lexile_max INTEGER NOT NULL,
            genres_json TEXT NOT NULL DEFAULT '[]',
            raw_text TEXT NOT NULL DEFAULT '',
            CHECK (lexile_min <= lexile_max)
        );

        CREATE TABLE IF NOT EXISTS recommendation_sessions (
            session_id TEXT PRIMARY KEY,
            phase TEXT NOT NULL
                CHECK (
                    phase IN (
                        'collecting_preferences',
                        'searching',
                        'awaiting_user',
                        'completed',
                        'failed'
                    )
                ),
            session_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS reading_lookup_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id TEXT NOT NULL,
            chapter_id TEXT NOT NULL,
            book_id TEXT NOT NULL,
            normalized_word TEXT NOT NULL,
            was_annotated INTEGER NOT NULL DEFAULT 0
                CHECK (was_annotated IN (0, 1)),
            looked_up_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS book_reading_support (
            book_id TEXT PRIMARY KEY,
            annotation_target INTEGER NOT NULL DEFAULT 8
                CHECK (annotation_target BETWEEN 1 AND 20),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS chapter_reading_checkpoints (
            book_id TEXT NOT NULL,
            chapter_id TEXT NOT NULL,
            chapter_no INTEGER NOT NULL,
            unit_ids_json TEXT NOT NULL,
            word_count INTEGER NOT NULL CHECK (word_count >= 0),
            lookup_count INTEGER NOT NULL CHECK (lookup_count >= 0),
            annotated_lookup_count INTEGER NOT NULL
                CHECK (
                    annotated_lookup_count >= 0
                    AND annotated_lookup_count <= lookup_count
                ),
            annotation_target INTEGER DEFAULT NULL
                CHECK (
                    annotation_target IS NULL
                    OR annotation_target BETWEEN 1 AND 20
                ),
            completed_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (book_id, chapter_id)
        );

        CREATE INDEX IF NOT EXISTS idx_units_book_chapter_section
            ON units(book_id, chapter_no, section_no);
        CREATE INDEX IF NOT EXISTS idx_units_chapter_id ON units(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_units_profile ON units(profile_id);
        CREATE INDEX IF NOT EXISTS idx_units_language ON units(language_id);
        CREATE INDEX IF NOT EXISTS idx_lexemes_language ON lexemes(language_id);
        CREATE INDEX IF NOT EXISTS idx_lexeme_mastery_mastered ON lexeme_mastery(mastered);
        CREATE INDEX IF NOT EXISTS idx_book_vocab_book ON book_vocabulary(book_id);
        CREATE INDEX IF NOT EXISTS idx_book_vocab_profile ON book_vocabulary(profile_id);
        CREATE INDEX IF NOT EXISTS idx_unit_vocab_unit ON unit_vocabulary(unit_id);
        CREATE INDEX IF NOT EXISTS idx_unit_vocab_chapter ON unit_vocabulary(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_bookmarks_unit ON bookmarks(unit_id);
        CREATE INDEX IF NOT EXISTS idx_recommendation_catalog_lexile
            ON recommendation_catalog(lexile_min, lexile_max);
        CREATE INDEX IF NOT EXISTS idx_recommendation_catalog_kind
            ON recommendation_catalog(entry_kind);
        CREATE INDEX IF NOT EXISTS idx_recommendation_sessions_phase_updated
            ON recommendation_sessions(phase, updated_at);
        CREATE INDEX IF NOT EXISTS idx_reading_lookup_events_book_time
            ON reading_lookup_events(book_id, looked_up_at);
        CREATE INDEX IF NOT EXISTS idx_reading_lookup_events_chapter
            ON reading_lookup_events(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_chapter_checkpoints_book_chapter
            ON chapter_reading_checkpoints(book_id, chapter_no);
        CREATE INDEX IF NOT EXISTS idx_reading_lookup_events_unit
            ON reading_lookup_events(unit_id);
        """
    )
    connection.commit()
