from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_POS = {"noun", "verb", "adjective", "adverb", "other"}
ALLOWED_DIFFICULTY = {"low", "medium", "high"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no}: row must be a JSON object")
            rows.append(value)
    return rows


def validate_row(row: dict[str, Any], *, row_no: int) -> list[str]:
    errors: list[str] = []
    for field in ("id", "word", "sentence", "gold"):
        if field not in row:
            errors.append(f"row {row_no}: missing {field}")

    if not isinstance(row.get("id"), str) or not row.get("id", "").strip():
        errors.append(f"row {row_no}: id must be a non-empty string")
    if not isinstance(row.get("word"), str) or not row.get("word", "").strip():
        errors.append(f"row {row_no}: word must be a non-empty string")
    if not isinstance(row.get("sentence"), str) or not row.get("sentence", "").strip():
        errors.append(f"row {row_no}: sentence must be a non-empty string")

    gold = row.get("gold")
    if not isinstance(gold, dict):
        errors.append(f"row {row_no}: gold must be an object")
        return errors

    for field in ("word_cn", "pos", "sentence_cn"):
        if not isinstance(gold.get(field), str) or not gold.get(field, "").strip():
            errors.append(f"row {row_no}: gold.{field} must be a non-empty string")

    pos = gold.get("pos")
    if isinstance(pos, str) and pos not in ALLOWED_POS:
        errors.append(f"row {row_no}: gold.pos {pos!r} is not allowed")

    difficulty = gold.get("difficulty")
    if difficulty is not None and difficulty not in ALLOWED_DIFFICULTY:
        errors.append(f"row {row_no}: gold.difficulty {difficulty!r} is not allowed")

    return errors


def validate_dataset(path: Path) -> list[str]:
    rows = load_jsonl(path)
    errors: list[str] = []
    seen_ids: set[str] = set()

    for index, row in enumerate(rows, start=1):
        errors.extend(validate_row(row, row_no=index))
        row_id = row.get("id")
        if isinstance(row_id, str):
            if row_id in seen_ids:
                errors.append(f"row {index}: duplicate id {row_id!r}")
            seen_ids.add(row_id)

    if not rows:
        errors.append("dataset is empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local lexicon JSONL data.")
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        help="Accepted for workflow clarity; validation uses stdlib checks.",
    )
    args = parser.parse_args()

    if args.schema and not args.schema.exists():
        raise SystemExit(f"schema not found: {args.schema}")

    errors = validate_dataset(args.path)
    if errors:
        for error in errors:
            print(error)
        return 1

    row_count = len(load_jsonl(args.path))
    print(f"ok: {args.path} ({row_count} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
