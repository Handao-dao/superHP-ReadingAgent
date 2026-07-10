"""English novel profile used by the current Harry Potter reader."""

from __future__ import annotations

import json
import re

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.contracts.annotation import AnnotationItem, ServiceIssue
from superhp_agent.profiles.base import CardCopy
from superhp_agent.profiles.validation import validate_annotation_output

ANNOTATION_POS = frozenset(
    {"noun", "verb", "adjective", "adverb", "phrase", "other"}
)

SYSTEM_POLICY = """
You are an expert English-Chinese reading assistant for the Harry Potter novels.
Help Chinese readers understand real reading obstacles while preserving the original reading experience.
""".strip()

ANNOTATION_CONTRACT = """
Input: one English passage from a Harry Potter chapter.
Output: the same passage text with selected difficult words or expressions replaced by inline annotations.

Preserve the original text exactly except for the selected replacements.
Do not rewrite, summarize, reorder, correct, add, or remove passage content.
Keep paragraph order, headings, line breaks, punctuation, casing, and spacing as close to the input as possible.

Inline annotation format: [[word or expression|中文翻译|pos]]
Use the exact original word or expression on the left side of the pipe.
Do not include the pipe character | inside the word, translation, or pos fields.
The Chinese translation must match the exact meaning in context.
Keep translations concise: prefer 1-4 Chinese characters; proper nouns or specialized terms may use up to 6 Chinese characters.
The pos value must be one of: noun, verb, adjective, adverb, phrase, other.
Use phrase for multi-word expressions, phrasal verbs, idioms, and fixed collocations.

If a phrase is the real difficult unit, annotate the whole phrase instead of separate words.
Prefer concise standard Chinese renderings for widely used Harry Potter proper nouns and magical terms.
Do not annotate ordinary character names such as Harry, Ron, Hermione, Dumbledore, or Hagrid unless the name itself is being explained as a title, place, spell, object, or special concept.
Do not duplicate the original word before or after the marker.
Correct: "a [[wand|魔杖|noun]]"
Incorrect: "a wand[[wand|魔杖|noun]]"
Incorrect: "a wand [[wand|魔杖|noun]]"
""".strip()

ANNOTATION_EXAMPLES = """
Input:
Harry picked up his wand and muttered a spell.

Good output:
Harry [[picked up|拿起|phrase]] his [[wand|魔杖|noun]] and [[muttered|低声说|verb]] a [[spell|咒语|noun]].

Bad output:
Harry picked up [[picked up|拿起|phrase]] his wand [[wand|魔杖|noun]] and muttered [[muttered|低声说|verb]] a spell [[spell|咒语|noun]].
Reason: duplicates original text instead of replacing the selected words or expression.
""".strip()

OUTPUT_CONTRACT = """
Return only the annotated passage text.
Do not output JSON.
Do not output a vocabulary list.
Do not wrap the answer in code fences.
Do not add explanations before or after the passage.
Do not add headings, summaries, or commentary unless they already exist in the input text.
""".strip()

MASTERED_WORDS_POLICY = """
Do not annotate any word or expression listed in mastered_words.
If mastered_words is an empty JSON array, ignore this block.
""".strip()

ANNOTATION_SYSTEM_BLOCKS = (
    ContextBlock("system_policy", SYSTEM_POLICY, role="system"),
    ContextBlock("annotation_contract", ANNOTATION_CONTRACT, role="system"),
    ContextBlock("annotation_examples", ANNOTATION_EXAMPLES, role="system"),
    ContextBlock("output_contract", OUTPUT_CONTRACT, role="system"),
)

BASE_ANNOTATOR_SYSTEM_PROMPT = ContextBundle(
    system_blocks=ANNOTATION_SYSTEM_BLOCKS,
).render_role("system")

LEVEL_PROFILES = {
    "beginner": {
        "ui": "H",
        "label": "a beginner English learner, roughly A1-A2 level",
        "density": "high",
        "target": "about 25%-40% of meaningful content words",
        "rules": (
            "Annotate frequently enough to help a beginner understand the text, "
            "but do not annotate every content word. "
            "Skip only very common function words and very basic everyday vocabulary. "
            "Annotate most content words beyond A1-A2 level, especially unfamiliar nouns, verbs, adjectives, and adverbs. "
            "Annotate all idioms, phrasal verbs, fixed expressions, culturally specific expressions, and wizarding-world terms that may affect understanding. "
            "For idioms and phrasal verbs, annotate the whole expression rather than individual words. "
            "Avoid repeated annotations of the same word within the same passage unless the meaning changes. "
            "Target annotation density: relatively high, about 25%-40% of meaningful content words."
        ),
    },
    "intermediate": {
        "ui": "M",
        "label": "an intermediate English learner, roughly B1-B2 level",
        "density": "medium",
        "target": "about 8%-18% of meaningful content words",
        "rules": (
            "Do not annotate A1-B1 high-frequency vocabulary that an intermediate learner should know. "
            "Focus on B2+ vocabulary, uncommon verbs, descriptive adjectives, adverbs with subtle meanings, "
            "less common nouns, literary words, wizarding-world terms, idioms, phrasal verbs, and words whose meaning depends strongly on context. "
            "Annotate culturally specific expressions and wizarding-world terms whose meaning is not obvious from the individual words. "
            "For idioms, phrasal verbs, and fixed expressions, annotate the whole expression rather than separate words. "
            "Avoid repeated annotations of the same word within the same passage unless necessary. "
            "Target annotation density: moderate, about 8%-18% of meaningful content words."
        ),
    },
    "advanced": {
        "ui": "L",
        "label": "an advanced English learner, roughly C1-C2 level",
        "density": "low",
        "target": "about 2%-6% of meaningful content words",
        "rules": (
            "Annotate only words or expressions that may challenge an advanced or near-fluent English reader. "
            "Do not annotate ordinary descriptive adjectives, common adverbs, common phrasal verbs, common idioms, "
            "or standard academic vocabulary. "
            "Focus only on truly rare, archaic, literary, metaphorical, dialectal, culturally specific, wizarding-world, or contextually subtle expressions. "
            "Annotate wizarding-world terms only if they are obscure, important for understanding the sentence, or appear for the first time as key terms. "
            "For complex expressions, annotate the whole phrase when appropriate rather than isolated words. "
            "When in doubt, do not annotate. "
            "Target annotation density: low, about 2%-6% of meaningful content words."
        ),
    },
}

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
    label = "English novel intensive reading"
    renderer_hint = "english_novel"
    card_copy = CardCopy()

    @property
    def base_annotator_system_prompt(self) -> str:
        return BASE_ANNOTATOR_SYSTEM_PROMPT

    @property
    def lookup_system_prompt(self) -> str:
        return LOOKUP_SYSTEM_PROMPT

    def normalize_level(self, level: str | None) -> str:
        if level in LEVEL_PROFILES:
            return str(level)
        return "intermediate"

    def build_annotator_context(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
    ) -> ContextBundle:
        return self.build_annotator_base_context(
            mastered_words=mastered_words,
            level=level,
        ).with_blocks(_reader_text_block(text))

    def build_annotator_base_context(
        self,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
    ) -> ContextBundle:
        return ContextBundle(
            system_blocks=ANNOTATION_SYSTEM_BLOCKS,
            user_blocks=(
                _density_profile_block(self.normalize_level(level)),
                _mastered_words_block(mastered_words),
                _mastered_words_policy_block(),
            ),
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


def _density_profile_block(level: str) -> ContextBlock:
    level_profile = LEVEL_PROFILES[level]
    content = (
        f"Target reader: {level_profile['label']}\n"
        f"Target density: {level_profile['target']}\n\n"
        f"{level_profile['rules']}"
    )
    return ContextBlock(
        "density_profile",
        content,
        role="user",
        attrs={
            "level": level,
            "ui": level_profile["ui"],
            "density": level_profile["density"],
        },
    )


def _mastered_words_block(mastered_words: list[str] | None) -> ContextBlock:
    return ContextBlock(
        "mastered_words",
        json.dumps(mastered_words or [], ensure_ascii=False),
        role="user",
    )


def _mastered_words_policy_block() -> ContextBlock:
    return ContextBlock("mastered_words_policy", MASTERED_WORDS_POLICY, role="user")


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
