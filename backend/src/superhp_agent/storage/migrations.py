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

        CREATE TABLE IF NOT EXISTS reading_companion_sessions (
            session_id TEXT PRIMARY KEY,
            reader_key TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('active', 'archived')),
            active_episode_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reading_companion_episodes (
            episode_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            trigger TEXT NOT NULL
                CHECK (
                    trigger IN (
                        'onboarding',
                        'manual_reading',
                        'difficulty_alert',
                        'user_request'
                    )
                ),
            start_message_id TEXT NOT NULL,
            state TEXT NOT NULL
                CHECK (state IN ('active', 'completed', 'abandoned')),
            book_id TEXT NOT NULL DEFAULT '',
            chapter_id TEXT NOT NULL DEFAULT '',
            unit_id TEXT NOT NULL DEFAULT '',
            selected_text TEXT NOT NULL DEFAULT '',
            end_message_id TEXT NOT NULL DEFAULT '',
            end_reason TEXT DEFAULT NULL,
            tool_call_count INTEGER NOT NULL DEFAULT 0
                CHECK (tool_call_count >= 0),
            error_code TEXT NOT NULL DEFAULT '',
            context_start_index INTEGER NOT NULL DEFAULT 0
                CHECK (context_start_index >= 0),
            created_at TEXT NOT NULL,
            ended_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (session_id)
                REFERENCES reading_companion_sessions(session_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reading_companion_messages (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
            content TEXT NOT NULL DEFAULT '',
            tool_calls_json TEXT NOT NULL DEFAULT '[]',
            tool_call_id TEXT NOT NULL DEFAULT '',
            tool_name TEXT NOT NULL DEFAULT '',
            is_error INTEGER NOT NULL DEFAULT 0
                CHECK (is_error IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE (episode_id, sequence_no),
            FOREIGN KEY (session_id)
                REFERENCES reading_companion_sessions(session_id)
                ON DELETE CASCADE,
            FOREIGN KEY (episode_id)
                REFERENCES reading_companion_episodes(episode_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS conversation_memories (
            memory_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            episode_id TEXT NOT NULL,
            kind TEXT NOT NULL
                CHECK (kind IN ('episode_summary', 'rolling_compaction')),
            revision INTEGER NOT NULL CHECK (revision >= 1),
            source_start_message_id TEXT NOT NULL,
            source_end_message_id TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('pending', 'ready', 'failed')),
            summary TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            input_tokens INTEGER NOT NULL DEFAULT 0
                CHECK (input_tokens >= 0),
            output_tokens INTEGER NOT NULL DEFAULT 0
                CHECK (output_tokens >= 0),
            created_at TEXT NOT NULL,
            UNIQUE (session_id, kind, revision),
            FOREIGN KEY (session_id)
                REFERENCES reading_companion_sessions(session_id)
                ON DELETE CASCADE,
            FOREIGN KEY (episode_id)
                REFERENCES reading_companion_episodes(episode_id)
                ON DELETE CASCADE,
            FOREIGN KEY (source_start_message_id)
                REFERENCES reading_companion_messages(message_id),
            FOREIGN KEY (source_end_message_id)
                REFERENCES reading_companion_messages(message_id)
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
            low_density_streak INTEGER NOT NULL DEFAULT 0
                CHECK (low_density_streak >= 0),
            max_target_high_density_streak INTEGER NOT NULL DEFAULT 0
                CHECK (max_target_high_density_streak >= 0),
            last_evaluated_chapter_id TEXT NOT NULL DEFAULT '',
            cooldown_chapters_remaining INTEGER NOT NULL DEFAULT 0
                CHECK (cooldown_chapters_remaining >= 0),
            last_decision TEXT NOT NULL DEFAULT '',
            last_uncovered_lookup_density REAL NOT NULL DEFAULT 0
                CHECK (last_uncovered_lookup_density >= 0),
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

        CREATE TABLE IF NOT EXISTS reading_difficulty_prompts (
            book_id TEXT PRIMARY KEY,
            chapter_id TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'pending',
                        'continue_reading',
                        'change_book'
                    )
                ),
            evidence_json TEXT NOT NULL,
            cooldown_chapters_remaining INTEGER NOT NULL DEFAULT 0
                CHECK (cooldown_chapters_remaining >= 0),
            last_cooldown_chapter_id TEXT NOT NULL DEFAULT '',
            recommendation_session_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
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
        CREATE INDEX IF NOT EXISTS idx_companion_sessions_reader_updated
            ON reading_companion_sessions(reader_key, updated_at);
        CREATE INDEX IF NOT EXISTS idx_companion_episodes_session_created
            ON reading_companion_episodes(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_companion_messages_episode_sequence
            ON reading_companion_messages(episode_id, sequence_no);
        CREATE INDEX IF NOT EXISTS idx_memories_session_kind_revision
            ON conversation_memories(session_id, kind, revision);
        CREATE INDEX IF NOT EXISTS idx_reading_lookup_events_book_time
            ON reading_lookup_events(book_id, looked_up_at);
        CREATE INDEX IF NOT EXISTS idx_reading_lookup_events_chapter
            ON reading_lookup_events(chapter_id);
        CREATE INDEX IF NOT EXISTS idx_chapter_checkpoints_book_chapter
            ON chapter_reading_checkpoints(book_id, chapter_no);
        CREATE INDEX IF NOT EXISTS idx_difficulty_prompts_status
            ON reading_difficulty_prompts(status);
        CREATE INDEX IF NOT EXISTS idx_reading_lookup_events_unit
            ON reading_lookup_events(unit_id);
        """
    )
    _ensure_column(
        connection,
        "reading_companion_episodes",
        "context_start_index",
        "INTEGER NOT NULL DEFAULT 0 CHECK (context_start_index >= 0)",
    )
    _ensure_column(
        connection,
        "book_reading_support",
        "low_density_streak",
        "INTEGER NOT NULL DEFAULT 0 CHECK (low_density_streak >= 0)",
    )
    _ensure_column(
        connection,
        "book_reading_support",
        "max_target_high_density_streak",
        (
            "INTEGER NOT NULL DEFAULT 0 "
            "CHECK (max_target_high_density_streak >= 0)"
        ),
    )
    _ensure_column(
        connection,
        "book_reading_support",
        "last_evaluated_chapter_id",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        connection,
        "book_reading_support",
        "cooldown_chapters_remaining",
        (
            "INTEGER NOT NULL DEFAULT 0 "
            "CHECK (cooldown_chapters_remaining >= 0)"
        ),
    )
    _ensure_column(
        connection,
        "book_reading_support",
        "last_decision",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        connection,
        "book_reading_support",
        "last_uncovered_lookup_density",
        (
            "REAL NOT NULL DEFAULT 0 "
            "CHECK (last_uncovered_lookup_density >= 0)"
        ),
    )
    connection.commit()


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """Add one backward-compatible column to an already-created local table."""
    existing = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )
