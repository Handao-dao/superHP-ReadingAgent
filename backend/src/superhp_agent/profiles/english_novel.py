"""English-novel prompts, labels, validation, and marker parsing policy."""

from __future__ import annotations

import json
import re

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.contracts.annotation import AnnotationItem, ServiceIssue
from superhp_agent.profiles.base import CardCopy
from superhp_agent.profiles.validation import validate_annotation_output

# New model output must use these exact labels. The parser remains tolerant of
# legacy saved markers so old reading artifacts can still be opened.
ANNOTATION_POS = frozenset(
    {"noun", "verb", "adjective", "adverb", "phrase", "other"}
)

SYSTEM_POLICY = """
You are an English-Chinese lexical annotation assistant for Chinese learners reading English novels, with particular familiarity with the Harry Potter series.

Add selective inline Chinese glosses without translating, rewriting, or otherwise altering the passage.

Prioritize exact source preservation, importance-based selection, and concise context-specific glosses, in that order.

Annotate only the words or expressions that most affect comprehension.
For approximately every 300 English words, normally use no more than 8 annotations.
Increase beyond 8 only when the passage contains an unusual concentration of indispensable comprehension obstacles, and never exceed 15 annotations.
These limits are not targets: do not use the extra capacity for lower-priority words, and use fewer annotations or none when appropriate.
""".strip()

ANNOTATION_CONTRACT = """
Transform one passage from an English novel by replacing selected source spans with inline annotations.

Source preservation:
- After replacing every annotation marker with its left-hand source field, the result must be character-for-character identical to the input.
- Do not rewrite, summarize, reorder, correct, add, or remove any other text.

Annotation syntax:
- Use [[exact source span|context-specific Chinese gloss|pos]].
- The source field must exactly match the text it replaces.
- Do not include |, [, or ] inside any field.
- Prefer one marker for the complete expression when that expression is the meaningful unit.
The pos value must be one of: noun, verb, adjective, adverb, phrase, other.
Use phrase for multi-word expressions, phrasal verbs, idioms, and fixed collocations.

Gloss quality:
- The Chinese gloss must match the source span's exact meaning in context.
- Keep the gloss as concise as the meaning allows.
""".strip()

# Corpus-specific guidance belongs in its own block so another novel series can
# replace it without changing the shared annotation contract or density policy.
HARRY_POTTER_SELECTION_POLICY = """
- Treat spells, magical objects, creatures, institutions, titles, and wizarding-world expressions as domain vocabulary.
- Do not select a term solely because it is magical, fictional, or capitalized.
- For a selected term, prefer its widely established Chinese rendering when one exists.
- Ordinary character names such as Harry, Ron, Hermione, Dumbledore, and Hagrid are not annotation targets.
""".strip()

ANNOTATION_EXAMPLES = """
Choose either a single word or a complete expression according to the smallest unit that carries the actual difficulty.

Single-word example input:
Harry remained bewildered as the portraits whispered among themselves and refused to explain what had happened.

Single-word example output:
Harry remained [[bewildered|困惑的|adjective]] as the portraits whispered among themselves and refused to explain what had happened.

Phrase example input:
Harry picked up his wand, looked toward the closed door, and muttered under his breath before returning to his seat.

Phrase example output:
Harry picked up his wand, looked toward the closed door, and [[muttered under his breath|低声嘟囔|phrase]] before returning to his seat.

Incorrect replacement:
Harry picked up his wand, looked toward the closed door, and muttered under his breath [[muttered under his breath|低声嘟囔|phrase]] before returning to his seat.

Reason:
The incorrect replacement duplicates the source expression instead of replacing it.
""".strip()

OUTPUT_CONTRACT = """
Return only the passage text with any selected inline annotations.
Do not output JSON, a vocabulary list, or a code fence.
Do not add any explanation or commentary around the passage.
If no annotation is needed, return the input passage unchanged.
""".strip()

MASTERED_WORDS_POLICY = """
Treat mastered_words as vocabulary the reader already understands.

- Do not annotate a source span that matches an entry in mastered_words, ignoring letter case and surrounding whitespace.
- A mastered component does not exclude a longer expression whose combined meaning is a genuine comprehension obstacle.
- If mastered_words is an empty JSON array, apply no mastery exclusions.
""".strip()

ANNOTATION_SYSTEM_BLOCKS = (
    ContextBlock("system_policy", SYSTEM_POLICY, role="system"),
    ContextBlock("annotation_contract", ANNOTATION_CONTRACT, role="system"),
    ContextBlock(
        "harry_potter_selection_policy",
        HARRY_POTTER_SELECTION_POLICY,
        role="system",
    ),
    ContextBlock("annotation_examples", ANNOTATION_EXAMPLES, role="system"),
    ContextBlock("mastered_words_policy", MASTERED_WORDS_POLICY, role="system"),
    ContextBlock("output_contract", OUTPUT_CONTRACT, role="system"),
)

BASE_ANNOTATOR_SYSTEM_PROMPT = ContextBundle(
    system_blocks=ANNOTATION_SYSTEM_BLOCKS,
).render_role("system")

LOOKUP_SYSTEM_PROMPT = """
# Role
You are an expert English-Chinese dictionary and translation assistant specialized in the Harry Potter novels.

Your job is to help Chinese readers understand a specific English word in context. You receive one word and the sentence containing it. You provide a concise Chinese translation of the word, a lightweight part-of-speech category, and a natural Chinese translation of the entire sentence.

# Rules
1. Word translation must match the exact meaning in context.
2. Keep the word translation concise. Prefer 1-4 Chinese characters.
3. The sentence translation should be natural Chinese, preserving the original meaning and tone.
4. The pos value must be one of: noun, verb, adjective, adverb, phrase, other.
5. Use phrase for multi-word expressions or fixed collocations. Use other when the category is unclear.
6. Do not add explanations, notes, or commentary.

# Output Rules
You must output valid JSON only.
Do not output Markdown.
Do not wrap the JSON in code fences.

# Output Format
{
  "word": "the original word",
  "word_cn": "中文翻译",
  "pos": "noun|verb|adjective|adverb|phrase|other",
  "sentence_cn": "整句中文翻译"
}
""".strip()

LOOKUP_USER_PROMPT_TEMPLATE = """
Word: {word}

Sentence:
<text>
{sentence}
</text>

Return only valid JSON in the required format.
""".strip()


class EnglishNovelProfile:
    """Default profile that preserves the current Harry Potter behavior."""

    id = "english_novel"
    language_id = "en"
    label = "English novel intensive reading"
    renderer_hint = "english_novel"
    card_copy = CardCopy()

    @property
    def base_annotator_system_prompt(self) -> str:
        return BASE_ANNOTATOR_SYSTEM_PROMPT

    @property
    def lookup_system_prompt(self) -> str:
        return LOOKUP_SYSTEM_PROMPT

    def build_annotator_context(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
    ) -> ContextBundle:
        return self.build_annotator_base_context(
            mastered_words=mastered_words,
        ).with_blocks(_reader_text_block(text))

    def build_annotator_base_context(
        self,
        *,
        mastered_words: list[str] | None = None,
    ) -> ContextBundle:
        return ContextBundle(
            system_blocks=ANNOTATION_SYSTEM_BLOCKS,
            user_blocks=(_mastered_words_block(mastered_words),),
        )

    def build_lookup_user_prompt(self, *, word: str, sentence: str) -> str:
        return LOOKUP_USER_PROMPT_TEMPLATE.format(word=word, sentence=sentence)

    def normalize_annotated_text(self, content: str) -> str:
        text = _strip_code_fence(content).strip()
        legacy_json_text = _extract_loose_annotated_text(text)
        if legacy_json_text is not None:
            text = legacy_json_text.strip()
        return text

    def validate_annotated_text(
        self,
        *,
        source_text: str,
        annotated_text: str,
    ) -> ServiceIssue | None:
        return validate_annotation_output(
            source_text=source_text,
            annotated_text=annotated_text,
            allowed_pos=ANNOTATION_POS,
        )

    def parse_annotation_items(self, text: str) -> list[AnnotationItem]:
        seen: set[str] = set()
        items: list[AnnotationItem] = []
        for match in re.finditer(r"\[\[([^|\]]+)\|([^|\]]+)(?:\|([^|\]]+))?\]\]", text):
            word = match.group(1).strip()
            translation = match.group(2).strip()
            pos = _normalize_marker_pos(match.group(3))
            key = word.lower()
            if not word or not translation or key in seen:
                continue
            seen.add(key)
            items.append(
                AnnotationItem(
                    word=word,
                    translation=translation,
                    context=_annotation_context(text, match.start()),
                    pos=pos,
                )
            )
        return items


def _mastered_words_block(mastered_words: list[str] | None) -> ContextBlock:
    return ContextBlock(
        "mastered_words",
        json.dumps(mastered_words or [], ensure_ascii=False),
        role="user",
    )


def _reader_text_block(text: str) -> ContextBlock:
    return ContextBlock("reader_text", text, role="user")


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _extract_loose_annotated_text(text: str) -> str | None:
    marker = '"annotated_text"'
    start = text.find(marker)
    if start < 0:
        return None
    colon = text.find(":", start + len(marker))
    if colon < 0:
        return None
    value = text[colon + 1 :].lstrip()
    if value.startswith('"'):
        value = value[1:]

    vocab_marker = re.search(r'"\s*,\s*"extracted_vocabulary"\s*:', value)
    if vocab_marker:
        value = value[: vocab_marker.start()]
    else:
        value = re.sub(r'"\s*}\s*$', "", value, flags=re.DOTALL)
        value = re.sub(r'"\s*,\s*}\s*$', "", value, flags=re.DOTALL)

    value = value.strip()
    if not value:
        return None
    return value.replace("\\n", "\n").replace('\\"', '"')


def _annotation_context(text: str, index: int) -> str:
    left = max(text.rfind(".", 0, index), text.rfind("!", 0, index), text.rfind("?", 0, index))
    right_candidates = [pos for pos in (text.find(".", index), text.find("!", index), text.find("?", index)) if pos >= 0]
    right = min(right_candidates) if right_candidates else min(len(text), index + 120)
    start = left + 1 if left >= 0 else max(0, index - 60)
    return re.sub(r"\s+", " ", text[start : right + 1]).strip()[:240]


def _normalize_marker_pos(pos: str | None) -> str:
    value = str(pos or "").strip().lower()
    aliases = {
        "n": "noun",
        "v": "verb",
        "adj": "adjective",
        "adv": "adverb",
    }
    value = aliases.get(value, value)
    return value if value in {"noun", "verb", "adjective", "adverb", "phrase", "other"} else "other"
