"""Pure vocabulary classification rules.

This module owns provider- and storage-neutral vocabulary normalization. It
does not parse model responses, access SQLite, build API DTOs, or choose a
profile-specific prompt.
"""

import re

VALID_POS = frozenset({
    "noun",
    "verb",
    "adjective",
    "adverb",
    "phrase",
    "other",
    "重点实词",
    "重点虚词",
    "通假字",
    "古今异义",
    "词类活用",
    "虚词用法",
    "特殊句式",
    "其他",
})

_POS_ALIASES = {
    "n": "noun",
    "v": "verb",
    "adj": "adjective",
    "adv": "adverb",
}

_ENGLISH_TOKEN_PATTERN = r"[A-Za-z0-9]+(?:[’'-][A-Za-z0-9]+)*"
_ENGLISH_TOKEN_RE = re.compile(_ENGLISH_TOKEN_PATTERN)
_ENGLISH_SPAN_RE = re.compile(
    rf"{_ENGLISH_TOKEN_PATTERN}(?:[ \t]+{_ENGLISH_TOKEN_PATTERN})*"
)
_CJK_SPAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def normalize_word(word: str | None) -> str:
    """Build the profile-local identity key for a displayed word or phrase."""
    return str(word or "").strip().casefold()


def extract_vocabulary_candidates(text: str, *, max_phrase_words: int = 4) -> set[str]:
    """Return normalized word and short-phrase identities found in source text.

    This is a lightweight retrieval tokenizer rather than a linguistic
    segmenter. Phrase generation is bounded so a chapter can be queried before
    concurrent model calls begin.
    """
    limit = max(1, int(max_phrase_words))
    candidates: set[str] = set()
    for match in _ENGLISH_SPAN_RE.finditer(text):
        english_tokens = [
            normalize_word(token) for token in _ENGLISH_TOKEN_RE.findall(match.group())
        ]
        for start in range(len(english_tokens)):
            for size in range(1, min(limit, len(english_tokens) - start) + 1):
                candidates.add(" ".join(english_tokens[start : start + size]))

    for match in _CJK_SPAN_RE.finditer(text):
        span = match.group()
        for start in range(len(span)):
            for size in range(1, min(limit, len(span) - start) + 1):
                candidates.add(span[start : start + size])
    return candidates


def normalize_pos(pos: str | None) -> str:
    """Normalize lightweight vocabulary part-of-speech labels."""
    raw = str(pos or "").strip()
    if raw in VALID_POS:
        return raw
    value = _POS_ALIASES.get(raw.lower(), raw.lower())
    return value if value in VALID_POS else "other"
