"""SQLite implementation of per-book annotation support persistence."""

from superhp_agent.domain.reading_support import (
    DEFAULT_ANNOTATION_TARGET,
    TARGET_CHANGE_COOLDOWN_CHAPTERS,
    ReadingSupportState,
    validate_annotation_target,
)
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteReadingSupportRepository:
    """Persist one current English annotation target per corpus book."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def get_annotation_target(self, book_id: str) -> int:
        return self.get_state(book_id).annotation_target

    def get_state(self, book_id: str) -> ReadingSupportState:
        book_id = self._require_book_id(book_id)
        with self.database.lock:
            row = self.database.connection.execute(
                """
                SELECT *
                FROM book_reading_support
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchone()
        if row is None:
            return ReadingSupportState(
                annotation_target=DEFAULT_ANNOTATION_TARGET
            )
        return _state_from_row(row)

    def set_annotation_target(
        self,
        book_id: str,
        annotation_target: int,
    ) -> None:
        book_id = self._require_book_id(book_id)
        annotation_target = validate_annotation_target(annotation_target)
        with self.database.lock:
            row = self.database.connection.execute(
                "SELECT * FROM book_reading_support WHERE book_id = ?",
                (book_id,),
            ).fetchone()
            current = (
                _state_from_row(row)
                if row is not None
                else ReadingSupportState()
            )
            changed = annotation_target != current.annotation_target
            next_state = ReadingSupportState(
                annotation_target=annotation_target,
                low_density_streak=(
                    0 if changed else current.low_density_streak
                ),
                max_target_high_density_streak=(
                    0
                    if changed
                    else current.max_target_high_density_streak
                ),
                last_evaluated_chapter_id=(
                    current.last_evaluated_chapter_id
                ),
                cooldown_chapters_remaining=(
                    TARGET_CHANGE_COOLDOWN_CHAPTERS
                    if changed
                    else current.cooldown_chapters_remaining
                ),
                last_decision=(
                    "target_changed" if changed else current.last_decision
                ),
                last_uncovered_lookup_density=(
                    current.last_uncovered_lookup_density
                ),
            )
            self._write_state(book_id, next_state)
            self.database.connection.commit()

    def save_evaluation_state(
        self,
        book_id: str,
        state: ReadingSupportState,
    ) -> None:
        book_id = self._require_book_id(book_id)
        with self.database.lock:
            self._write_state(book_id, state)
            self.database.connection.commit()

    def _write_state(
        self,
        book_id: str,
        state: ReadingSupportState,
    ) -> None:
        self.database.connection.execute(
            """
            INSERT INTO book_reading_support (
                book_id,
                annotation_target,
                low_density_streak,
                max_target_high_density_streak,
                last_evaluated_chapter_id,
                cooldown_chapters_remaining,
                last_decision,
                last_uncovered_lookup_density,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(book_id) DO UPDATE SET
                annotation_target=excluded.annotation_target,
                low_density_streak=excluded.low_density_streak,
                max_target_high_density_streak=excluded.max_target_high_density_streak,
                last_evaluated_chapter_id=excluded.last_evaluated_chapter_id,
                cooldown_chapters_remaining=excluded.cooldown_chapters_remaining,
                last_decision=excluded.last_decision,
                last_uncovered_lookup_density=excluded.last_uncovered_lookup_density,
                updated_at=excluded.updated_at
            """,
            (
                book_id,
                state.annotation_target,
                state.low_density_streak,
                state.max_target_high_density_streak,
                state.last_evaluated_chapter_id,
                state.cooldown_chapters_remaining,
                state.last_decision,
                state.last_uncovered_lookup_density,
            ),
        )

    @staticmethod
    def _require_book_id(book_id: str) -> str:
        value = str(book_id or "").strip()
        if not value:
            raise ValueError("book_id is required")
        return value


def _state_from_row(row) -> ReadingSupportState:
    return ReadingSupportState(
        annotation_target=int(row["annotation_target"]),
        low_density_streak=int(row["low_density_streak"]),
        max_target_high_density_streak=int(
            row["max_target_high_density_streak"]
        ),
        last_evaluated_chapter_id=str(
            row["last_evaluated_chapter_id"] or ""
        ),
        cooldown_chapters_remaining=int(
            row["cooldown_chapters_remaining"]
        ),
        last_decision=str(row["last_decision"] or ""),
        last_uncovered_lookup_density=float(
            row["last_uncovered_lookup_density"]
        ),
        updated_at=str(row["updated_at"] or ""),
    )
