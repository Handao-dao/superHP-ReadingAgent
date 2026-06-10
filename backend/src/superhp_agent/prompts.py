"""Prompt builders for chapter annotation and word lookup."""

from __future__ import annotations

import json

BASE_ANNOTATOR_SYSTEM_PROMPT = """
# Role
You are an expert English-Chinese reading assistant for the Harry Potter novels.

Your job is to help Chinese readers understand real reading obstacles while preserving the original reading experience.

# Task
You will receive one English passage from a Harry Potter chapter.

You must:
1. Identify words or expressions that may confuse the target English learner.
2. Replace each selected word or expression with the [[word|translation]] format.
3. Return the full annotated passage text only.

# Annotation Rules
1. Preserve the original text exactly. Do not rewrite, summarize, reorder, or correct the input text.
2. Only annotate selected words or expressions by replacing that exact text with [[word|translation]].
3. Use double square brackets, English word or phrase, pipe character |, Chinese translation.
4. Do not include the pipe character | inside the word or translation text.
5. The Chinese translation must match the exact meaning in context.
6. Keep translations concise. Prefer 1-4 Chinese characters. For proper nouns or specialized terms, up to 6 Chinese characters is acceptable.
7. Prioritize British colloquial expressions, everyday object vocabulary, wizarding-world terms, magical objects, school titles, spells, charms, currency, creatures, house-related terms, and common-looking words with special meanings in this universe.
8. Do not annotate ordinary character names such as Harry, Ron, Hermione, Dumbledore, or Hagrid unless the name itself is being explained as a title, place, spell, object, or special concept.
9. If a phrase is the real difficult unit, annotate the whole phrase instead of a single word.
10. If the same word appears multiple times in the text, you may annotate it each time.
11. For proper nouns and magical terms, prefer concise standard Chinese renderings where they are widely used.
12. Do not duplicate the original word before or after the marker. Correct: "a [[wand|魔杖]]"; incorrect: "a wand[[wand|魔杖]]" or "a wand [[wand|魔杖]]".

# Output Rules
Return only the annotated passage text.
Do not output JSON.
Do not output a vocabulary list.
Do not wrap the answer in code fences.
Do not add explanations before or after the passage.
Do not add headings, summaries, or commentary unless they already exist in the input text.
""".strip()

LEVEL_PROFILES = {
    "beginner": {
        "label": "a beginner English learner, roughly A1-A2 level",
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
        "label": "an intermediate English learner, roughly B1-B2 level",
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
        "label": "an advanced English learner, roughly C1-C2 level",
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

ANNOTATOR_USER_PROMPT_TEMPLATE = """
Please annotate the following Harry Potter text for {level_label}.

# Annotation Level Rules
{level_rules}

Mastered words:
{mastered_words}

Rules for mastered words:
- Do not annotate any word or expression listed in mastered_words.
- If mastered_words is empty, ignore this section.

Original text:
<text>
{text}
</text>

Return only the annotated passage text.
""".strip()

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


def normalize_level(level: str | None) -> str:
    if level in LEVEL_PROFILES:
        return level
    return "intermediate"


def build_annotator_user_prompt(
    text: str,
    mastered_words: list[str] | None = None,
    level: str = "intermediate",
) -> str:
    mastered_words = mastered_words or []
    level_profile = LEVEL_PROFILES[normalize_level(level)]
    return ANNOTATOR_USER_PROMPT_TEMPLATE.format(
        level_label=level_profile["label"],
        level_rules=level_profile["rules"],
        mastered_words=json.dumps(mastered_words, ensure_ascii=False),
        text=text,
    )


def build_lookup_user_prompt(word: str, sentence: str) -> str:
    return LOOKUP_USER_PROMPT_TEMPLATE.format(word=word, sentence=sentence)
