"""Compatibility prompt exports for the default annotation profile."""

from __future__ import annotations

from superhp_agent.context import ContextBundle
from superhp_agent.profiles import english_novel

SYSTEM_POLICY = english_novel.SYSTEM_POLICY
ANNOTATION_CONTRACT = english_novel.ANNOTATION_CONTRACT
ANNOTATION_EXAMPLES = english_novel.ANNOTATION_EXAMPLES
OUTPUT_CONTRACT = english_novel.OUTPUT_CONTRACT
MASTERED_WORDS_POLICY = english_novel.MASTERED_WORDS_POLICY
ANNOTATION_SYSTEM_BLOCKS = english_novel.ANNOTATION_SYSTEM_BLOCKS
BASE_ANNOTATOR_SYSTEM_PROMPT = english_novel.BASE_ANNOTATOR_SYSTEM_PROMPT
LEVEL_PROFILES = english_novel.LEVEL_PROFILES
LOOKUP_SYSTEM_PROMPT = english_novel.LOOKUP_SYSTEM_PROMPT
LOOKUP_USER_PROMPT_TEMPLATE = english_novel.LOOKUP_USER_PROMPT_TEMPLATE

_DEFAULT_PROFILE = english_novel.EnglishNovelProfile()


def normalize_level(level: str | None) -> str:
    return _DEFAULT_PROFILE.normalize_level(level)


def build_annotator_context(
    text: str,
    mastered_words: list[str] | None = None,
    level: str = "intermediate",
) -> ContextBundle:
    return _DEFAULT_PROFILE.build_annotator_context(
        text,
        mastered_words=mastered_words,
        level=level,
    )


def build_annotator_base_context(
    mastered_words: list[str] | None = None,
    level: str = "intermediate",
) -> ContextBundle:
    return _DEFAULT_PROFILE.build_annotator_base_context(
        mastered_words=mastered_words,
        level=level,
    )


def build_annotator_user_prompt(
    text: str,
    mastered_words: list[str] | None = None,
    level: str = "intermediate",
) -> str:
    return build_annotator_context(text, mastered_words=mastered_words, level=level).render_role("user")


def build_lookup_user_prompt(word: str, sentence: str) -> str:
    return _DEFAULT_PROFILE.build_lookup_user_prompt(word=word, sentence=sentence)
