# Reading Agent 本地词义消歧模型训练与评测规划

> Status: working draft. This file keeps the initial plan in-repo so later
> design decisions can be discussed, edited, and tracked alongside code.

## 1. 项目定位

本项目不是单独训练一个通用聊天模型，而是作为 `Reading Agent -- 英文阅读助手` 的二阶段能力升级：

> 为点击查词场景构建一个本地可部署的上下文词义消歧模型，实现 `word + context -> word_cn / sentence_cn / pos`，并通过 SFT / DPO / 评测 / 本地部署形成完整闭环。

核心目标：

- 将原本依赖云端 LLM 的点击查词能力，部分替换为本地小模型推理。
- 针对英文原著阅读场景，提升多义词在上下文中的释义准确率。
- 让模型稳定输出结构化 JSON，便于后端直接解析和前端渲染。
- 建立一套可复现实验流程：数据构造、微调、评测、部署、接入。

MiniMind 可作为理解 LLM 训练链路的补充学习材料，但不作为主项目经历。主项目叙事应围绕 Reading Agent 的真实业务场景展开。

## 2. 总体技术路线

整体流水线：

```text
Reading Agent 原始语料 / 英文原著文本
  -> 抽取 word + context 样本
  -> 使用强模型 / 词典 / 人工校验生成标注
  -> 构建 SFT 数据集
  -> 使用 HuggingFace 模型 + LoRA/QLoRA 微调
  -> 构建评测集并对比 base / SFT / SFT+DPO
  -> 构造 chosen / rejected 偏好数据
  -> 进行 DPO 训练
  -> 合并 LoRA / 转换量化模型
  -> 使用 Ollama 或 llama.cpp 本地部署
  -> 接入 Reading Agent Provider 层
```

工具分工：

| 模块 | 推荐工具 | 作用 |
| --- | --- | --- |
| 基础模型 | HuggingFace Transformers | 加载和训练开源模型 |
| 快速微调 | LLaMA-Factory | 低代码跑通 SFT / DPO / LoRA |
| 深入实现 | TRL + PEFT | 手写/理解 SFTTrainer、DPOTrainer、LoRA |
| 数据处理 | datasets / pandas | 构造、清洗、切分数据集 |
| 结构校验 | jsonschema / pydantic | 验证模型输出格式 |
| 评测脚本 | Python 自写 | 计算定制任务指标 |
| 本地部署 | Ollama / llama.cpp | 提供本地推理 API |
| 系统接入 | FastAPI Provider 层 | 接入 Reading Agent 点击查词模块 |

## 3. 模型选择建议

第一阶段优先选择小尺寸 instruct 模型，降低训练和部署难度。

候选模型：

- `Qwen2.5-0.5B-Instruct`
- `Qwen2.5-1.5B-Instruct`
- `Qwen3-0.6B` 或同级别小模型
- `Phi` / `Gemma` 系列小模型，视本地硬件支持情况选择

建议顺序：

1. 先用 instruct 模型做 SFT，快速得到可用效果。
2. 再尝试 base model + SFT，理解指令能力如何被训练出来。
3. 如果本地显存有限，优先使用 LoRA / QLoRA，而不是全参数微调。

Ollama 的定位：

- Ollama 主要用于本地推理和应用接入。
- 微调主流程应使用 LLaMA-Factory 或 TRL + PEFT。
- 训练完成后，再将模型转换或量化为适合 Ollama / llama.cpp 部署的格式。

## 4. 数据格式设计

### 4.0 当前字段决策

第一版继承 Reading Agent 现有查词服务契约，不扩展线上输出字段：

- 输入：`word` + `sentence`
- 输出：`word`、`word_cn`、`pos`、`sentence_cn`

其中：

- `word_cn`：目标单词在当前上下文中的中文释义。
- `sentence_cn`：包含目标单词的整句中文翻译。
- `pos`：目标单词词性，第一版只训练 `noun / verb / adjective / adverb / other`。

虽然后端批量译注 marker 里存在 `phrase`，但当前点击查词服务实际还不能支持词组查询，因此本地查词模型第一版不训练 `phrase`，也不把 `sense` 作为模型输出字段。多义词消歧能力通过 `word_cn` 与 `sentence_cn` 的上下文一致性来体现。

### 4.1 接入边界决策

第一版本地模型调用统一继承项目现有 `LLMProvider` 抽象，不单独设计 `LexiconLookupEngine`。

原因：

- 当前 `WordLookupService` 已经只依赖 `LLMProvider.chat_with_retry()`，服务边界足够薄。
- 本地模型可以通过 OpenAI-compatible API、Ollama 兼容接口，或新增 provider 实现接入同一抽象。
- 统一 provider 能复用现有重试、错误归一化、配置创建和 lazy service 逻辑。
- 查词服务的业务契约保持不变，后续 fallback 到云端 provider 更自然。

实现含义：

- `WordLookupService` 继续负责 prompt、JSON 抽取、字段归一化。
- 本地模型适配放在 provider/factory/config 层，而不是在 service 层开新分支。
- 第一版可以优先验证“本地 OpenAI-compatible endpoint + 现有 `OpenAICompatProvider`”是否足够；不够时再新增专门的 local provider。

### 4.2 SFT 数据

任务形式：

```text
输入：目标单词 + 出现上下文
输出：结构化 JSON，包括目标单词、单词翻译、整句翻译、词性
```

样例：

```json
{
  "instruction": "Given a target English word and its context, return structured Chinese reading assistance.",
  "input": {
    "word": "charge",
    "sentence": "The creature made a sudden charge across the room."
  },
  "output": {
    "word": "charge",
    "word_cn": "冲锋",
    "pos": "noun",
    "sentence_cn": "那个生物突然冲过房间。"
  }
}
```

推荐字段：

| 字段 | 含义 |
| --- | --- |
| `word` | 原始目标单词 |
| `word_cn` | 目标词在当前上下文中的中文释义 |
| `sentence_cn` | 包含目标词的整句中文翻译 |
| `pos` | 词性或短语类别 |

当前不保留可选输出字段。`difficulty` 对阅读产品可能有价值，但本任务主要评测上下文查词能力；加入难度会增加标注负担和不必要噪声。

### 4.3 DPO 数据

DPO 用于强化“上下文词义选择”，不是第一阶段必需项。

样例：

```json
{
  "prompt": "word: charge\nsentence: The creature made a sudden charge across the room.",
  "chosen": {
    "word": "charge",
    "word_cn": "冲锋",
    "pos": "noun",
    "sentence_cn": "那个生物突然冲过房间。"
  },
  "rejected": {
    "word": "charge",
    "word_cn": "收费",
    "pos": "verb",
    "sentence_cn": "那个生物突然向房间收费。"
  }
}
```

适合构造 DPO 数据的词：

- `charge`
- `issue`
- `fine`
- `fair`
- `present`
- `object`
- `sentence`
- `scale`
- `figure`
- `bound`

chosen / rejected 的设计重点：

- chosen 必须符合上下文。
- rejected 可以是常见但不适合当前上下文的义项。
- rejected 不应是明显胡言乱语，否则模型学不到细粒度偏好。

### 4.4 评测数据

评测集必须和训练集分离，建议人工抽查修正。

样例：

```json
{
  "word": "issue",
  "sentence": "The publisher will issue a new edition next month.",
  "gold": {
    "word_cn": "发行",
    "pos": "verb",
    "sentence_cn": "出版商将在下个月发行新版。"
  }
}
```

建议规模：

- 第一版 SFT 训练集：1000 到 5000 条。
- 第一版评测集：200 到 500 条。
- 第一版 DPO 数据：500 到 2000 对 chosen / rejected。

## 5. 分阶段实施计划

### 阶段 0：Baseline 与任务定义

目标：在不训练的情况下，明确现有模型的能力上限和问题。

任务：

- 选定一个基础模型。
- 编写固定 prompt，让模型输出目标 JSON。
- 用 100 到 200 条样本测试格式稳定性和词义准确性。
- 记录 base model 的 JSON 合法率、字段完整率、词性准确率、词义准确率。

交付物：

- `baseline_prompt.md`
- `eval_seed.jsonl`
- `baseline_report.md`

判断标准：

- 明确 base model 在点击查词任务上的主要失败类型。
- 确认微调是否有必要。

### 阶段 1：SFT 数据构造

目标：构建第一版可训练数据集。

任务：

- 从 Reading Agent 语料或英文原著中抽取句子。
- 选择目标词，优先覆盖多义词、高频词、短语动词、阅读中断点。
- 使用强模型生成初版标注。
- 对评测集进行人工抽查和修正。
- 统一输出 schema。

交付物：

- `train_sft.jsonl`
- `eval.jsonl`
- `schema.json`
- `data_card.md`

判断标准：

- 训练集字段稳定。
- 评测集质量高于训练集，不能完全依赖自动生成。

### 阶段 2：SFT / LoRA 微调

目标：让模型稳定完成结构化查词任务。

推荐工具：

- 第一轮：LLaMA-Factory
- 第二轮：TRL + PEFT 复刻最小训练脚本

任务：

- 使用 LoRA 或 QLoRA 进行 SFT。
- 控制输出格式为 JSON。
- 保存 adapter 和训练配置。
- 对比 base model 与 SFT model 的评测结果。

交付物：

- `sft_config.yaml`
- `adapter/`
- `sft_eval_report.md`
- `train_logs/`

判断标准：

- JSON 合法率明显提升。
- 字段完整率明显提升。
- 词性和上下文词义准确率有可观提升。

### 阶段 3：评测体系建设

目标：建立项目厚度最关键的一层，即可复现的自动评测。

评测指标：

| 指标 | 含义 |
| --- | --- |
| JSON valid rate | 输出是否是合法 JSON |
| schema complete rate | 必需字段是否完整 |
| extra text rate | JSON 外是否有多余文本 |
| POS accuracy | 词性是否正确 |
| word translation accuracy | `word_cn` 是否符合上下文 |
| sentence translation quality | `sentence_cn` 是否自然且含义正确 |
| target consistency | 单词释义是否和整句翻译一致 |
| latency | 平均推理延迟 |
| fallback rate | 本地模型失败后回退云端的比例 |

建议脚本结构：

```text
eval/
  run_eval.py
  metrics.py
  schema.py
  report.py
  cases/
    eval.jsonl
```

任务：

- 编写统一推理接口，支持 base / SFT / DPO 模型。
- 编写 JSON 解析和 schema 校验。
- 计算格式类指标。
- 对 `pos` 做精确匹配。
- 对 `word_cn` 和 `sentence_cn` 做人工标注匹配、规则近似或 teacher model 评估。
- 输出 CSV / Markdown 报告。

交付物：

- `eval_report_base_vs_sft.md`
- `eval_results.csv`
- `error_cases.jsonl`

判断标准：

- 评测脚本可以重复运行。
- 报告能解释模型提升和退化，而不只是给一个总分。

### 阶段 4：DPO 偏好优化

目标：进一步提升多义词上下文选择能力。

任务：

- 从评测错误和高频多义词中构造 chosen / rejected 样本。
- 使用 LLaMA-Factory 或 TRL DPOTrainer 训练 DPO。
- 对比 SFT 与 SFT+DPO。
- 检查 DPO 是否导致格式稳定性退化。

交付物：

- `train_dpo.jsonl`
- `dpo_config.yaml`
- `dpo_eval_report.md`

判断标准：

- 上下文词义准确率有提升。
- JSON valid rate 不应明显下降。
- 如果 DPO 提升很小，也应在报告中说明原因。

### 阶段 5：本地部署与 Reading Agent 接入

目标：让训练成果进入真实应用。

任务：

- 合并 LoRA 或保留 adapter 推理。
- 根据部署方案转换格式，必要时转 GGUF 并量化。
- 使用 Ollama 或 llama.cpp 提供本地推理服务。
- 通过 Reading Agent 现有 `LLMProvider` 抽象接入本地模型；优先尝试 OpenAI-compatible 本地端点复用 `OpenAICompatProvider`，必要时再新增 `LocalLexiconProvider`。
- 点击查词优先走本地模型。
- 解析失败、超时或置信度不足时 fallback 到云端 LLM。

建议调用链：

```text
Frontend click word
  -> FastAPI word lookup endpoint
  -> WordLookupService
  -> LLMProvider configured for local lexicon model
  -> local model inference
  -> JSON schema validation
  -> return structured result
  -> fallback to cloud provider if failed
```

交付物：

- 本地模型 provider 配置或 `LocalLexiconProvider`
- 本地推理启动脚本
- Provider fallback 策略
- 接入前后延迟和成本对比报告

判断标准：

- 本地查词可在真实阅读流程中使用。
- 响应延迟可接受。
- 失败时不会破坏主流程。

## 6. 推荐目录结构

可在 Reading Agent 项目中新增类似结构：

```text
local_lexicon_model/
  README.md
  data/
    raw/
    processed/
    train_sft.jsonl
    train_dpo.jsonl
    eval.jsonl
  configs/
    sft_config.yaml
    dpo_config.yaml
  scripts/
    build_dataset.py
    validate_dataset.py
    run_inference.py
  eval/
    run_eval.py
    metrics.py
    report.py
  reports/
    baseline_report.md
    sft_eval_report.md
    dpo_eval_report.md
  deployment/
    ollama/
    llama_cpp/
```

## 7. 简历表达建议

不要写成：

> 学习 MiniMind，了解大模型训练流程。

推荐写成：

> 本地词义消歧模型：面向英文原著点击查词场景，构建 `word + sentence -> JSON` 结构化数据集，基于 HuggingFace 小模型进行 LoRA/SFT 微调，并引入 DPO 样本强化上下文词义选择；设计 JSON 合法率、词性准确率、词义一致性和延迟等评测指标，将本地模型接入 Reading Agent Provider 层，替代部分云端 LLM 查询。

更偏 Agent 实习的写法：

> 在 Reading Agent 中设计本地 Lexicon Model 子系统，将点击查词从纯 Prompt 调用升级为可训练、可评测、可部署的模型服务；通过 Provider 抽象实现本地模型优先、云端 LLM fallback 的混合推理策略，并用自动评测报告追踪 SFT/DPO 对结构化输出和上下文词义消歧的影响。

## 8. 风险与取舍

主要风险：

- 小模型可能翻译质量有限。
- 自动生成数据会带来噪声。
- DPO 收益不一定稳定。
- Windows 本地训练环境可能受 CUDA、bitsandbytes、WSL2 等因素影响。
- Ollama 部署和训练框架之间存在格式转换成本。

取舍建议：

- 第一版不要追求 RL，先完成 SFT + 评测 + 接入。
- DPO 作为第二阶段加分项。
- MiniMind 作为训练原理补充，不作为主线项目。
- 与其追求模型大，不如追求任务边界清楚、评测扎实、系统能跑通。

## 9. 第一周可执行计划

第 1 天：

- 选定基础模型。
- 写出固定 prompt 和输出 schema。
- 准备 50 到 100 条手工或半自动样本。

第 2 天：

- 写 baseline 推理脚本。
- 跑 base model，收集错误案例。

第 3 天：

- 扩展 SFT 数据到 1000 条左右。
- 单独整理 100 到 200 条评测集。

第 4 天：

- 使用 LLaMA-Factory 跑第一版 LoRA/SFT。

第 5 天：

- 写评测脚本，输出 base vs SFT 报告。

第 6 天：

- 分析错误案例，构造第一批 DPO chosen/rejected 数据。

第 7 天：

- 决定是否进入 DPO；如果 SFT 效果已经足够，优先做 Reading Agent 接入。

## 10. 最小可交付版本

MVP 不要求完成 DPO 或 RL。

最低可交付目标：

- 1 个本地小模型 LoRA/SFT adapter。
- 1 套 `word + context -> JSON` 数据集。
- 1 个可重复运行的评测脚本。
- 1 份 base vs SFT 评测报告。
- 1 个 Reading Agent Provider 层接入原型。

达到这一层后，项目已经可以写进简历。DPO、RL、MiniMind 复现都可以作为后续增强。

## 11. 待商议问题

下面这些点需要在正式实施前对齐：

- 线上 API 契约已决定坚持四字段 `word / word_cn / pos / sentence_cn`；第一版训练和评测不保留额外输出字段 `sense`。
- 本地模型已决定接入通用 `LLMProvider`；第一版不单独设计 `LexiconLookupEngine`。
- 第一阶段 baseline 使用 Ollama、llama.cpp，还是直接使用 Transformers 本地推理。
- 数据来源是否只使用项目 `corpus/`，还是引入公开例句、词典义项和人工构造多义词样本。
- 评测中的词义准确率用人工标注、规则近似、teacher model，还是三者组合。
- 失败回退策略如何定义：JSON 解析失败、schema 缺字段、低置信度、超时，分别如何处理。
- 小模型输出是否必须严格 JSON，还是允许本地 adapter 层做容错抽取。
- 第一版已决定不训练 `phrase`；后续如果查词服务支持词组，再扩展 pos 集合和数据 schema。
- 第一版是否真的进入 DPO，还是先完成 SFT + 评测 + Provider 接入 MVP。
