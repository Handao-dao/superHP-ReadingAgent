"""Pure vocabulary classification rules.

This module owns provider- and storage-neutral vocabulary normalization. It
does not parse model responses, access SQLite, build API DTOs, or choose a
profile-specific prompt.
"""

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


def normalize_pos(pos: str | None) -> str:
    """Normalize lightweight vocabulary part-of-speech labels."""
    raw = str(pos or "").strip()
    if raw in VALID_POS:
        return raw
    value = _POS_ALIASES.get(raw.lower(), raw.lower())
    return value if value in VALID_POS else "other"
