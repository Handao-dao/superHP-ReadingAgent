from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


REQUIRED_FIELDS = ("word_cn", "pos", "sentence_cn")


@dataclass(frozen=True)
class CaseScore:
    id: str
    json_valid: bool
    schema_complete: bool
    extra_text: bool
    pos_correct: bool
    word_cn_exact: bool


def extract_json_object(text: str) -> tuple[dict[str, Any] | None, bool]:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        return (value if isinstance(value, dict) else None), False
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, bool(stripped)

    try:
        value = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None, True
    return (value if isinstance(value, dict) else None), start > 0 or end < len(stripped) - 1


def score_case(gold_row: dict[str, Any], prediction_text: str) -> CaseScore:
    payload, extra_text = extract_json_object(prediction_text)
    gold = gold_row["gold"]
    json_valid = payload is not None
    schema_complete = bool(
        payload
        and all(isinstance(payload.get(field), str) and payload[field].strip() for field in REQUIRED_FIELDS)
    )
    return CaseScore(
        id=str(gold_row["id"]),
        json_valid=json_valid,
        schema_complete=schema_complete,
        extra_text=extra_text,
        pos_correct=bool(payload and payload.get("pos") == gold.get("pos")),
        word_cn_exact=bool(payload and payload.get("word_cn") == gold.get("word_cn")),
    )


def aggregate(scores: list[CaseScore]) -> dict[str, float]:
    total = len(scores)
    if total == 0:
        return {
            "count": 0,
            "json_valid_rate": 0.0,
            "schema_complete_rate": 0.0,
            "extra_text_rate": 0.0,
            "pos_accuracy": 0.0,
            "word_cn_exact_rate": 0.0,
        }

    def rate(attr: str) -> float:
        return sum(1 for score in scores if getattr(score, attr)) / total

    return {
        "count": float(total),
        "json_valid_rate": rate("json_valid"),
        "schema_complete_rate": rate("schema_complete"),
        "extra_text_rate": rate("extra_text"),
        "pos_accuracy": rate("pos_correct"),
        "word_cn_exact_rate": rate("word_cn_exact"),
    }

