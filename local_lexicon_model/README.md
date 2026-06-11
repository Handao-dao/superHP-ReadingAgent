# Local Lexicon Model

This directory is an isolated lab for the Reading Agent click-to-lookup model.
It is intentionally separate from `backend/` so dataset experiments, baseline
tests, SFT/DPO configs, and reports can evolve without touching the production
word lookup service.

## Goal

Train and evaluate a small local model for:

```text
word + sentence context -> structured Chinese lookup JSON
```

The runtime contract should stay compatible with the existing Reading Agent
lookup API:

```json
{
  "word": "spell",
  "word_cn": "咒语",
  "pos": "noun",
  "sentence_cn": "他念了一个咒语。"
}
```

Training and evaluation should keep the same four output fields in the first
iteration. Phrase lookup is out of scope for now, so local model datasets should
not use `phrase` as a POS label.

## Directory Layout

```text
local_lexicon_model/
  README.md
  baseline_prompt.md
  data/
    raw/
    processed/
    eval_seed.jsonl
    schema.json
  configs/
    sft_config.yaml
    dpo_config.yaml
  scripts/
    validate_dataset.py
  eval/
    metrics.py
    run_eval.py
  reports/
    baseline_report.md
  deployment/
    ollama/
    llama_cpp/
```

## Phases

1. Baseline: run a fixed prompt against a base model and measure format,
   translation, and POS failures.
2. Dataset: build SFT examples and a separately checked evaluation set.
3. SFT: train a LoRA/QLoRA adapter and compare against the baseline.
4. DPO: add chosen/rejected pairs for difficult polysemous cases.
5. Deployment: expose local inference through an `LLMProvider` implementation
   or an OpenAI-compatible local endpoint, then configure lookup to use it with
   cloud fallback.

## Data Contracts

Evaluation rows use this shape:

```json
{
  "id": "eval-0001",
  "word": "charge",
  "sentence": "The creature made a sudden charge across the room.",
  "gold": {
    "word_cn": "冲锋",
    "pos": "noun",
    "sentence_cn": "那个生物突然冲过房间。"
  }
}
```

SFT rows can use either an instruction-tuning shape or this same normalized
shape. Keep the normalized shape as the source of truth, then export to the
framework-specific format required by LLaMA-Factory or TRL.

## Quick Checks

Validate the seed evaluation set:

```powershell
python local_lexicon_model/scripts/validate_dataset.py local_lexicon_model/data/eval_seed.jsonl --schema local_lexicon_model/data/schema.json
```

Score a JSONL prediction file against the seed set:

```powershell
python local_lexicon_model/eval/run_eval.py --gold local_lexicon_model/data/eval_seed.jsonl --pred local_lexicon_model/reports/predictions.example.jsonl
```
