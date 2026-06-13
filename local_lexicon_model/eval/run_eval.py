from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from metrics import aggregate, aggregate_by, extract_json_object, score_case


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
    parser.add_argument("--error-output", type=Path)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    args = parser.parse_args()

    gold_rows = {str(row["id"]): row for row in load_jsonl(args.gold)}
    pred_rows = load_jsonl(args.pred)

    scores = []
    error_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    pred_by_id = {str(row.get("id")): row for row in pred_rows}
    for case_id, gold_row in gold_rows.items():
        pred_row = pred_by_id.get(case_id)
        if pred_row is None:
            missing.append(case_id)
            continue
        prediction_text = str(pred_row.get("prediction", ""))
        score = score_case(gold_row, prediction_text)
        scores.append(score)
        payload, _ = extract_json_object(prediction_text)
        comparison_rows.append(
            build_comparison_row(
                gold_row=gold_row,
                pred_row=pred_row,
                prediction=payload,
                score=score,
                raw_prediction=prediction_text,
            )
        )
        if score.error_kinds:
            error_rows.append(
                {
                    "id": case_id,
                    "error_kinds": list(score.error_kinds),
                    "word": gold_row.get("word"),
                    "sentence": gold_row.get("sentence"),
                    "source": gold_row.get("source"),
                    "gold": gold_row.get("gold"),
                    "prediction": payload,
                    "raw_prediction": prediction_text,
                    "latency_ms": pred_row.get("latency_ms"),
                    "provider_error": pred_row.get("error"),
                }
            )

    latencies = [
        float(row["latency_ms"])
        for row in pred_rows
        if isinstance(row.get("latency_ms"), int | float)
    ]
    result = {
        **aggregate(scores),
        "missing_count": float(len(missing)),
        "error_case_count": float(len(error_rows)),
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "by_pos": aggregate_by(scores, "gold_pos"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.error_output:
        args.error_output.parent.mkdir(parents=True, exist_ok=True)
        with args.error_output.open("w", encoding="utf-8") as file:
            for row in error_rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.report_output:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(render_markdown_report(result), encoding="utf-8")

    if args.csv_output:
        write_csv(args.csv_output, comparison_rows)

    if missing:
        print(f"missing predictions: {', '.join(missing)}")
        return 1
    return 0


def build_comparison_row(
    *,
    gold_row: dict[str, Any],
    pred_row: dict[str, Any],
    prediction: dict[str, Any] | None,
    score: Any,
    raw_prediction: str,
) -> dict[str, Any]:
    gold = gold_row.get("gold") or {}
    source = gold_row.get("source") or {}
    prediction = prediction or {}
    return {
        "id": gold_row.get("id", ""),
        "source_path": source.get("path", ""),
        "word": gold_row.get("word", ""),
        "sentence": gold_row.get("sentence", ""),
        "gold_word_cn": gold.get("word_cn", ""),
        "pred_word_cn": prediction.get("word_cn", ""),
        "gold_pos": gold.get("pos", ""),
        "pred_pos": prediction.get("pos", ""),
        "gold_sentence_cn": gold.get("sentence_cn", ""),
        "pred_sentence_cn": prediction.get("sentence_cn", ""),
        "json_valid": int(score.json_valid),
        "schema_complete": int(score.schema_complete),
        "extra_text": int(score.extra_text),
        "pos_correct": int(score.pos_correct),
        "word_cn_exact": int(score.word_cn_exact),
        "sentence_cn_exact": int(score.sentence_cn_exact),
        "error_kinds": ",".join(score.error_kinds),
        "latency_ms": pred_row.get("latency_ms", ""),
        "provider_error": pred_row.get("error", ""),
        "raw_prediction": raw_prediction,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "source_path",
        "word",
        "sentence",
        "gold_word_cn",
        "pred_word_cn",
        "gold_pos",
        "pred_pos",
        "gold_sentence_cn",
        "pred_sentence_cn",
        "json_valid",
        "schema_complete",
        "extra_text",
        "pos_correct",
        "word_cn_exact",
        "sentence_cn_exact",
        "error_kinds",
        "latency_ms",
        "provider_error",
        "raw_prediction",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Local Lexicon Evaluation Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key in (
        "count",
        "json_valid_rate",
        "schema_complete_rate",
        "extra_text_rate",
        "pos_accuracy",
        "word_cn_exact_rate",
        "sentence_cn_exact_rate",
        "all_core_exact_rate",
        "avg_latency_ms",
        "error_case_count",
    ):
        value = result.get(key, 0)
        lines.append(f"| {key} | {format_value(value)} |")

    lines.extend(["", "## By POS", "", "| Group | Count | POS Acc | Word CN Exact | Core Exact |", "| --- | ---: | ---: | ---: | ---: |"])
    for group, metrics in result.get("by_pos", {}).items():
        lines.append(
            "| "
            f"{group} | "
            f"{format_value(metrics.get('count', 0))} | "
            f"{format_value(metrics.get('pos_accuracy', 0))} | "
            f"{format_value(metrics.get('word_cn_exact_rate', 0))} | "
            f"{format_value(metrics.get('all_core_exact_rate', 0))} |"
        )

    return "\n".join(lines) + "\n"


def format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
