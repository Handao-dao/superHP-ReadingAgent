"""Profile interfaces for text-specific annotation policy.

A Profile owns prompts, marker rules, output normalization, validation, and
parsing for one reading scenario. It never calls a Provider, persists data, or
emits transport events; those responsibilities stay in Service and Runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from superhp_agent.context import ContextBundle
from superhp_agent.contracts.annotation import AnnotationItem, ServiceIssue


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
    unit_body_template: str = "{prefix}: {book_title}, Chapter {chapter_no}, {chapter_title}."
    review_body_template: str = "{prefix} This chapter currently has {count} {scope} {item_label}."
    generate_annotation_label: str = "Generate"
    open_annotated_label: str = "Annotated"
    read_original_label: str = "Original"
    review_items_label: str = "Vocab"
    start_next_label: str = "Next"


class AnnotationProfile(Protocol):
    """Text policy required by annotation and lookup services."""

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

    def validate_annotated_text(
        self,
        *,
        source_text: str,
        annotated_text: str,
    ) -> ServiceIssue | None: ...

    def parse_annotation_items(self, text: str) -> list[AnnotationItem]: ...
