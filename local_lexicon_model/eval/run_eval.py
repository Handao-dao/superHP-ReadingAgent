from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from metrics import aggregate, score_case


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate local lexicon predictions.")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--pred", type=Path, required=True)
    args = parser.parse_args()

    gold_rows = {str(row["id"]): row for row in load_jsonl(args.gold)}
    pred_rows = load_jsonl(args.pred)

    scores = []
    missing: list[str] = []
    for case_id, gold_row in gold_rows.items():
        pred_row = next((row for row in pred_rows if str(row.get("id")) == case_id), None)
        if pred_row is None:
            missing.append(case_id)
            continue
        prediction_text = str(pred_row.get("prediction", ""))
        scores.append(score_case(gold_row, prediction_text))

    result = aggregate(scores)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if missing:
        print(f"missing predictions: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

