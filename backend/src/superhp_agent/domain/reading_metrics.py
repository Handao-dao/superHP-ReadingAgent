"""Pure text metrics shared by reading observation components."""

import re

_ENGLISH_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[’'-][A-Za-z0-9]+)*")


def count_english_words(text: str) -> int:
    """Estimate English word count while ignoring punctuation."""
    return len(_ENGLISH_WORD_RE.findall(str(text or "")))


def density_per_300(count: int, word_count: int) -> float:
    """Normalize one non-negative count to a per-300-word density."""
    if count < 0:
        raise ValueError("count must not be negative")
    if word_count <= 0:
        return 0.0
    return round(count / word_count * 300, 2)
