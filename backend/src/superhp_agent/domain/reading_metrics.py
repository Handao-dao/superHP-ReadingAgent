"""Pure text metrics shared by reading observation components."""

import re

_ENGLISH_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[’'-][A-Za-z0-9]+)*")


def count_english_words(text: str) -> int:
    """Estimate English word count while ignoring punctuation."""
    return len(_ENGLISH_WORD_RE.findall(str(text or "")))
