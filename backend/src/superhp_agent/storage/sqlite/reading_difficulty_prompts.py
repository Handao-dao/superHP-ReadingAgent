"""SQLite persistence for the latest per-book difficulty prompt."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

from superhp_agent.contracts import ReadingDifficultyEvidence
from superhp_agent.domain.reading_difficulty_prompt import (
    ReadingDifficultyPrompt,
    ReadingDifficultyPromptStatus,
)
from superhp_agent.storage.database import SQLiteDatabase


class SQLiteReadingDifficultyPromptRepository:
    """Store prompt evidence, user choice, cooldown, and Agent linkage."""

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def get(self, book_id: str) -> ReadingDifficultyPrompt | None:
        book_id = _require_text(book_id, "book_id")
        with self.database.lock:
            row = self.database.connection.execute(
                """
                SELECT *
                FROM reading_difficulty_prompts
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchone()
        return _prompt_from_row(row) if row is not None else None

    def open_prompt(
        self,
        *,
        book_id: str,
        chapter_id: str,
        evidence: ReadingDifficultyEvidence,
    ) -> ReadingDifficultyPrompt:
        prompt = ReadingDifficultyPrompt(
            book_id=_require_text(book_id, "book_id"),
            chapter_id=_require_text(chapter_id, "chapter_id"),
            status=ReadingDifficultyPromptStatus.PENDING,
            evidence=evidence,
        )
        return self._save(prompt)

    def choose_continue(
        self,
        book_id: str,
        *,
        cooldown_chapters: int,
    ) -> ReadingDifficultyPrompt:
        if cooldown_chapters < 0:
            raise ValueError("cooldown_chapters must not be negative")
        current = self._require_prompt(book_id)
        if current.status is ReadingDifficultyPromptStatus.CONTINUE_READING:
            return current
        if current.status is not ReadingDifficultyPromptStatus.PENDING:
            raise ValueError("difficulty prompt is not awaiting a choice")
        return self._save(
            replace(
                current,
                status=ReadingDifficultyPromptStatus.CONTINUE_READING,
                cooldown_chapters_remaining=cooldown_chapters,
                last_cooldown_chapter_id=current.chapter_id,
                recommendation_session_id="",
            )
        )

    def choose_change_book(
        self,
        book_id: str,
        *,
        recommendation_session_id: str,
    ) -> ReadingDifficultyPrompt:
        session_id = _require_text(
            recommendation_session_id,
            "recommendation_session_id",
        )
        current = self._require_prompt(book_id)
        if current.status is ReadingDifficultyPromptStatus.CHANGE_BOOK:
            if current.recommendation_session_id != session_id:
                raise ValueError(
                    "difficulty prompt is linked to another session"
                )
            return current
        if current.status is not ReadingDifficultyPromptStatus.PENDING:
            raise ValueError("difficulty prompt is not awaiting a choice")
        return self._save(
            replace(
                current,
                status=ReadingDifficultyPromptStatus.CHANGE_BOOK,
                cooldown_chapters_remaining=0,
                last_cooldown_chapter_id=current.chapter_id,
                recommendation_session_id=session_id,
            )
        )

    def advance_cooldown(
        self,
        book_id: str,
        *,
        chapter_id: str,
    ) -> ReadingDifficultyPrompt | None:
        current = self.get(book_id)
        if current is None:
            return None
        chapter_id = _require_text(chapter_id, "chapter_id")
        if (
            current.status
            is not ReadingDifficultyPromptStatus.CONTINUE_READING
            or current.cooldown_chapters_remaining <= 0
            or current.last_cooldown_chapter_id == chapter_id
        ):
            return current
        return self._save(
            replace(
                current,
                cooldown_chapters_remaining=(
                    current.cooldown_chapters_remaining - 1
                ),
                last_cooldown_chapter_id=chapter_id,
            )
        )

    def _require_prompt(self, book_id: str) -> ReadingDifficultyPrompt:
        prompt = self.get(book_id)
        if prompt is None:
            raise ValueError("difficulty prompt not found")
        return prompt

    def _save(
        self,
        prompt: ReadingDifficultyPrompt,
    ) -> ReadingDifficultyPrompt:
        evidence_json = json.dumps(
            asdict(prompt.evidence),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.database.lock:
            self.database.connection.execute(
                """
                INSERT INTO reading_difficulty_prompts (
                    book_id,
                    chapter_id,
                    status,
                    evidence_json,
                    cooldown_chapters_remaining,
                    last_cooldown_chapter_id,
                    recommendation_session_id,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(book_id) DO UPDATE SET
                    chapter_id=excluded.chapter_id,
                    status=excluded.status,
                    evidence_json=excluded.evidence_json,
                    cooldown_chapters_remaining=excluded.cooldown_chapters_remaining,
                    last_cooldown_chapter_id=excluded.last_cooldown_chapter_id,
                    recommendation_session_id=excluded.recommendation_session_id,
                    updated_at=excluded.updated_at
                """,
                (
                    prompt.book_id,
                    prompt.chapter_id,
                    prompt.status.value,
                    evidence_json,
                    prompt.cooldown_chapters_remaining,
                    prompt.last_cooldown_chapter_id,
                    prompt.recommendation_session_id,
                ),
            )
            self.database.connection.commit()
        stored = self.get(prompt.book_id)
        assert stored is not None
        return stored


def _prompt_from_row(row) -> ReadingDifficultyPrompt:
    evidence = json.loads(str(row["evidence_json"]))
    return ReadingDifficultyPrompt(
        book_id=str(row["book_id"]),
        chapter_id=str(row["chapter_id"]),
        status=ReadingDifficultyPromptStatus(str(row["status"])),
        evidence=ReadingDifficultyEvidence(**evidence),
        cooldown_chapters_remaining=int(
            row["cooldown_chapters_remaining"]
        ),
        last_cooldown_chapter_id=str(
            row["last_cooldown_chapter_id"] or ""
        ),
        recommendation_session_id=str(
            row["recommendation_session_id"] or ""
        ),
        updated_at=str(row["updated_at"] or ""),
    )


def _require_text(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized
