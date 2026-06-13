"""Profile interfaces for text annotation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from superhp_agent.context import ContextBundle


@dataclass(frozen=True)
class AnnotationItem:
    """One learning item extracted from profile-specific annotation output."""

    word: str
    translation: str
    context: str
    pos: str = "other"


@dataclass(frozen=True)
class CardCopy:
    """User-facing copy used by deterministic guided cards."""

    empty_title: str = "No Reading Texts Yet"
    empty_body: str = "Add chapter Markdown files to the corpus/ directory first."
    start_title: str = "Ready to Read"
    start_prefix: str = "Next up"
    complete_title: str = "Chapter Complete"
    final_complete_title: str = "Final Chapter Complete"
    complete_prefix: str = "You can move on."
    back_to_annotated_label: str = "Back to Annotated"
    back_to_source_label: str = "Back to Original"
    learning_item_singular: str = "word"
    learning_item_plural: str = "words"
    learning_item_scope: str = "vocabulary"


class AnnotationProfile(Protocol):
    """Capabilities supplied by one text-learning profile."""

    id: str
    label: str
    renderer_hint: str
    card_copy: CardCopy

    def normalize_level(self, level: str | None) -> str: ...

    def build_annotator_base_context(
        self,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
    ) -> ContextBundle: ...

    def build_lookup_user_prompt(self, *, word: str, sentence: str) -> str: ...

    @property
    def lookup_system_prompt(self) -> str: ...

    @property
    def base_annotator_system_prompt(self) -> str: ...

    def normalize_annotated_text(self, content: str) -> str: ...

    def parse_annotation_items(self, text: str) -> list[AnnotationItem]: ...

