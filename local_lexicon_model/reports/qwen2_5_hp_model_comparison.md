# Qwen2.5 HP Lookup Baseline Comparison

Dataset: `local_lexicon_model/data/eval_samples_hp.jsonl`

| Model | JSON Valid | Schema Complete | POS Acc | Word CN Exact | Sentence CN Exact | Core Exact | Avg Latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen2.5:1.5b | 0.980 | 0.980 | 0.756 | 0.258 | 0.068 | 0.226 | 322.869 ms |
| qwen2.5:3b | 0.996 | 0.996 | 0.678 | 0.304 | 0.050 | 0.220 | 412.738 ms |

## By POS

| Model | POS | Count | POS Acc | Word CN Exact | Core Exact |
| --- | --- | ---: | ---: | ---: | ---: |
| qwen2.5:1.5b | adjective | 93 | 0.882 | 0.215 | 0.215 |
| qwen2.5:1.5b | adverb | 53 | 0.906 | 0.264 | 0.264 |
| qwen2.5:1.5b | noun | 56 | 0.411 | 0.375 | 0.196 |
| qwen2.5:1.5b | verb | 298 | 0.755 | 0.248 | 0.228 |
| qwen2.5:3b | adjective | 93 | 0.892 | 0.398 | 0.376 |
| qwen2.5:3b | adverb | 53 | 0.962 | 0.491 | 0.491 |
| qwen2.5:3b | noun | 56 | 0.089 | 0.411 | 0.054 |
| qwen2.5:3b | verb | 298 | 0.671 | 0.221 | 0.154 |

## Notes

- `qwen2.5:3b` improves JSON validity and strict `word_cn` matching, especially on adjectives and adverbs.
- `qwen2.5:3b` regresses on POS accuracy, mainly because noun cases are often mislabeled.
- Exact Chinese translation metrics are strict string matches and should be followed by semantic judging.
- `qwen2.5:1.5b` is faster and has better overall POS accuracy in this run.

