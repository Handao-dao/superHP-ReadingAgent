from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from superhp_agent.providers.base import GenerationSettings
from superhp_agent.providers.openai_compat import OpenAICompatProvider
from superhp_agent.providers.registry import ProviderSpec
from superhp_agent.prompts import LOOKUP_SYSTEM_PROMPT, build_lookup_user_prompt
from superhp_agent.storage import normalize_pos
from superhp_agent.utils import extract_json


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def load_done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if row.get("id"):
                done.add(str(row["id"]))
    return done


async def run(args: argparse.Namespace) -> int:
    if importlib.util.find_spec("openai") is None:
        raise RuntimeError(
            "Missing Python package 'openai'. Run this script inside the backend "
            "environment, for example: cd backend; uv run python "
            "../local_lexicon_model/scripts/run_ollama_baseline.py --model "
            f"{args.model}"
        )

    provider = OpenAICompatProvider(
        api_key=args.api_key,
        api_base=args.base_url,
        default_model=args.model,
        timeout=args.timeout,
        spec=ProviderSpec(
            name="ollama",
            keywords=("ollama",),
            display_name="Ollama OpenAI-compatible",
            requires_api_key=False,
        ),
    )
    provider.generation = GenerationSettings(
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    rows = load_jsonl(args.input)
    done_ids = load_done_ids(args.output) if args.resume else set()
    pending_rows = [row for row in rows if str(row["id"]) not in done_ids]
    args.output.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if args.resume else "w"
    if done_ids:
        print(f"resuming: {len(done_ids)} done, {len(pending_rows)} pending")
    with args.output.open(mode, encoding="utf-8") as file:
        for index, row in enumerate(pending_rows, start=1):
            started = time.perf_counter()
            record: dict[str, Any] = {"id": row["id"]}
            try:
                result = await lookup_word(
                    provider=provider,
                    word=str(row["word"]),
                    sentence=str(row["sentence"]),
                )
                record["prediction"] = json.dumps(result, ensure_ascii=False)
                record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            except Exception as exc:
                record["prediction"] = ""
                record["error"] = str(exc)
                record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            file.flush()
            if args.progress_every > 0 and index % args.progress_every == 0:
                print(f"processed {index}/{len(pending_rows)} pending")

    print(f"wrote {args.output}")
    return 0


async def lookup_word(
    *,
    provider: OpenAICompatProvider,
    word: str,
    sentence: str,
) -> dict[str, str]:
    response = await provider.chat_with_retry(
        messages=[
            {"role": "system", "content": LOOKUP_SYSTEM_PROMPT},
            {"role": "user", "content": build_lookup_user_prompt(word=word, sentence=sentence)},
        ],
    )
    if response.is_error:
        raise RuntimeError(response.content or "LLM lookup request failed")
    if not response.content:
        raise ValueError("LLM returned empty lookup response")

    payload = extract_json(response.content)
    return {
        "word": str(payload.get("word") or word),
        "word_cn": str(payload.get("word_cn") or ""),
        "pos": normalize_pos(payload.get("pos")),
        "sentence_cn": str(payload.get("sentence_cn") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run local lexicon baseline through Ollama's OpenAI-compatible API."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "local_lexicon_model" / "data" / "eval_seed.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "local_lexicon_model" / "reports" / "ollama_predictions.jsonl",
    )
    parser.add_argument("--model", default="qwen2.5:1.5b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--api-key", default="ollama")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--progress-every", type=int, default=25)
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
