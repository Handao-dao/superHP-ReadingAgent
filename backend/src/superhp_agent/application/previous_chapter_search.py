"""Search summaries and source paragraphs inside a trusted reading scope.

The service accepts an already-authorized ``PreviousReadingScope`` and returns
bounded evidence grouped by chapter. It does not build access scope, inspect
the current chapter, generate an Agent answer, or expose Corpus file paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from superhp_agent.contracts import (
    PreviousChapterExcerpt,
    PreviousChapterMatch,
    PreviousChapterSearchRequest,
    PreviousChapterSearchResult,
)
from superhp_agent.corpus import CorpusError, CorpusStore, ReadingUnit


class PreviousChapterSearchError(RuntimeError):
    """Stable application error that a future Tool can map to JSON."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PreviousChapterSearchPolicy:
    """Internal evidence limits independent from model-selected chapter count."""

    max_excerpts_per_chapter: int = 2
    max_excerpt_chars: int = 500

    def __post_init__(self) -> None:
        if not 1 <= self.max_excerpts_per_chapter <= 5:
            raise ValueError("max_excerpts_per_chapter must be between 1 and 5")
        if not 100 <= self.max_excerpt_chars <= 2000:
            raise ValueError("max_excerpt_chars must be between 100 and 2000")


@dataclass(frozen=True)
class _ChapterCandidate:
    match: PreviousChapterMatch
    score: int
    evidence_truncated: bool = False


class PreviousChapterSearchService:
    """Find keyword evidence without reading beyond the supplied scope."""

    def __init__(
        self,
        corpus: CorpusStore,
        *,
        policy: PreviousChapterSearchPolicy | None = None,
    ):
        self.corpus = corpus
        self.policy = policy or PreviousChapterSearchPolicy()

    def search(
        self,
        request: PreviousChapterSearchRequest,
    ) -> PreviousChapterSearchResult:
        """Search authorized summaries and source paragraphs."""
        patterns = _query_patterns(request.query)
        try:
            units_by_id = {
                unit.id: unit for unit in self.corpus.list_units()
            }
        except (CorpusError, OSError) as exc:
            raise PreviousChapterSearchError(
                "corpus_unavailable",
                "The reading corpus is unavailable.",
            ) from exc

        candidates: list[_ChapterCandidate] = []
        for chapter in request.scope.completed_chapters:
            chapter_units = tuple(
                self._require_scoped_unit(
                    units_by_id,
                    unit_id,
                    request,
                    chapter.chapter_id,
                    chapter.chapter_no,
                )
                for unit_id in chapter.unit_ids
            )
            candidate = self._search_chapter(
                request,
                chapter_units,
                patterns,
            )
            if candidate is not None:
                candidates.append(candidate)

        ranked = sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                -candidate.match.chapter_no,
                candidate.match.chapter_id,
            ),
        )
        selected = ranked[: request.max_chapters]
        matches = tuple(
            candidate.match
            for candidate in sorted(
                selected,
                key=lambda candidate: (
                    candidate.match.chapter_no,
                    candidate.match.chapter_id,
                ),
            )
        )
        return PreviousChapterSearchResult(
            request=request,
            matches=matches,
            truncated=(
                len(ranked) > request.max_chapters
                or any(
                    candidate.evidence_truncated
                    for candidate in selected
                )
            ),
        )

    def _search_chapter(
        self,
        request: PreviousChapterSearchRequest,
        chapter_units: tuple[ReadingUnit, ...],
        patterns: tuple[str, ...],
    ) -> _ChapterCandidate | None:
        """Collect one chapter's summary and bounded matching paragraphs."""
        summaries = tuple(
            dict.fromkeys(
                unit.summary.strip()
                for unit in chapter_units
                if unit.summary.strip()
            )
        )
        summary = "\n".join(summaries)
        summary_score = _match_score(summary, patterns)
        source_score = 0
        excerpts: list[PreviousChapterExcerpt] = []
        evidence_truncated = False

        for unit in chapter_units:
            try:
                document = self.corpus.get_unit(unit.id)
            except (CorpusError, OSError) as exc:
                raise PreviousChapterSearchError(
                    "corpus_unavailable",
                    "The reading corpus is unavailable.",
                ) from exc
            if document.meta != unit:
                raise PreviousChapterSearchError(
                    "scope_stale",
                    "The reading corpus changed after scope construction.",
                )

            for paragraph in _paragraphs(document.body):
                paragraph_score = _match_score(paragraph, patterns)
                if paragraph_score == 0:
                    continue
                source_score += paragraph_score
                if len(excerpts) < self.policy.max_excerpts_per_chapter:
                    excerpts.append(
                        PreviousChapterExcerpt(
                            unit_id=unit.id,
                            text=_bounded_excerpt(
                                paragraph,
                                patterns,
                                self.policy.max_excerpt_chars,
                            ),
                        )
                    )
                else:
                    evidence_truncated = True

        if summary_score == 0 and source_score == 0:
            return None

        first = chapter_units[0]
        return _ChapterCandidate(
            match=PreviousChapterMatch(
                chapter_id=first.chapter_id,
                chapter_no=first.chapter_no,
                chapter_title=first.chapter_title,
                summary=summary,
                excerpts=tuple(excerpts),
            ),
            score=summary_score * 2 + source_score,
            evidence_truncated=evidence_truncated,
        )

    @staticmethod
    def _require_scoped_unit(
        units_by_id: dict[str, ReadingUnit],
        unit_id: str,
        request: PreviousChapterSearchRequest,
        chapter_id: str,
        chapter_no: int,
    ) -> ReadingUnit:
        """Revalidate scope against current Corpus metadata before reading."""
        unit = units_by_id.get(unit_id)
        if (
            unit is None
            or unit.book_id != request.scope.book_id
            or unit.chapter_id != chapter_id
            or unit.chapter_no != chapter_no
            or not unit.chapter_title.strip()
        ):
            raise PreviousChapterSearchError(
                "scope_stale",
                "The trusted reading scope no longer matches the corpus.",
            )
        return unit


def _query_patterns(query: str) -> tuple[str, ...]:
    """Keep an exact phrase plus simple Unicode word-like terms."""
    phrase = " ".join(query.casefold().split())
    terms = re.findall(
        r"[^\W_]+(?:['’-][^\W_]+)*",
        phrase,
        flags=re.UNICODE,
    )
    return tuple(dict.fromkeys((phrase, *(term for term in terms if term != phrase))))


def _match_score(text: str, patterns: tuple[str, ...]) -> int:
    """Return a small deterministic relevance score for literal matches."""
    normalized = text.casefold()
    if not normalized:
        return 0
    score = len(_match_positions(normalized, patterns[0])) * 4
    return score + sum(
        len(_match_positions(normalized, pattern))
        for pattern in patterns[1:]
    )


def _match_positions(text: str, pattern: str) -> tuple[int, ...]:
    """Avoid matching a short Latin query inside an unrelated longer word."""
    if re.fullmatch(r"[a-z0-9'’\-\s]+", pattern):
        expression = (
            rf"(?<![a-z0-9_]){re.escape(pattern)}(?![a-z0-9_])"
        )
        return tuple(match.start() for match in re.finditer(expression, text))

    positions: list[int] = []
    start = 0
    while (position := text.find(pattern, start)) >= 0:
        positions.append(position)
        start = position + max(1, len(pattern))
    return tuple(positions)


def _paragraphs(body: str) -> tuple[str, ...]:
    """Split source Markdown into non-empty paragraph-sized evidence."""
    return tuple(
        paragraph.strip()
        for paragraph in re.split(r"\r?\n\s*\r?\n+", body)
        if paragraph.strip()
    )


def _bounded_excerpt(
    paragraph: str,
    patterns: tuple[str, ...],
    max_chars: int,
) -> str:
    """Crop a long paragraph around its first matching phrase or term."""
    if len(paragraph) <= max_chars:
        return paragraph

    normalized = paragraph.casefold()
    positions: list[int] = []
    for pattern in patterns:
        matches = _match_positions(normalized, pattern)
        if matches:
            positions.append(matches[0])
    match_at = min(positions, default=0)
    content_budget = max_chars - 2
    start = max(0, match_at - content_budget // 3)
    end = min(len(paragraph), start + content_budget)
    start = max(0, end - content_budget)
    prefix = "…" if start else ""
    suffix = "…" if end < len(paragraph) else ""
    return f"{prefix}{paragraph[start:end].strip()}{suffix}"
