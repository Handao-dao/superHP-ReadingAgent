# Service 层说明

本文记录 `services/` 内业务服务的职责边界和运行语义。项目整体分层见上一级
[`README.md`](../README.md)，后端功能总览见 [`BACKEND_OVERVIEW.md`](../../../BACKEND_OVERVIEW.md)。

## 职责边界

Service 负责完成一个明确的后端业务任务，例如译注生成和上下文查词。它可以组合
Profile、Context 和 Provider Port，但不负责：

- 接收 HTTP 或 WebSocket 消息。
- 决定阅读流程和前端 Cards。
- 直接操作 SQLite、Memory 或译注文件。
- 把模型返回错误直接拼成 Transport 协议。

Provider 负责模型 SDK、请求参数和瞬时错误重试；Service 负责判断最终模型结果在当前业务中
是否可用，并以 Contracts 中的结构化结果向上层传递状态。

## 英文译注 Context 组织

英文小说是当前产品主路径。译注 Context 按“稳定规则 → 整章任务数据 → 当前 chunk”
的顺序组织：

```text
System / Static
    system_policy
    annotation_contract
    selection_policy（可选的系列补充）
    annotation_examples
    mastered_words_policy
    output_contract

User / Chapter Task
    mastered_words

User / Chunk Data
    reader_text
```

各 block 的职责如下：

- `system_policy`：定义英文词汇译注任务、优先级和统一密度。
- `annotation_contract`：定义 marker 格式、POS、原文还原不变式和释义质量。
- `selection_policy`：可选的系列特色补充；普通英文小说不生成此 block。当前仅哈利波特系列使用，其他小说直接采用通用规则。
- `annotation_examples`：演示单词、完整短语和错误重复替换。
- `mastered_words_policy`：解释熟词排除以及熟词作为更长表达组成部分时的边界。
- `output_contract`：约束响应外壳，并明确零标注时原样返回输入。

英文译注不再按高、中、低分级。每约 300 个英文单词通常不超过 8 处标注；只有局部必要难点密集时
才可超过 8 处，但绝对不超过 15 处。上限不是必须凑满的配额。Prompt 仍要求模型尽量保持原文，
但阅读主链路不再使用逐字符一致性作为整块成功与否的判定条件。

标注边界以单词为优先；只有固定搭配、习语或拆开后会丢失、误解整体含义的特殊表达，才整体标注为 phrase。

### 整章复用与 prompt caching

Dispatcher 在并发译注前一次性准备整章相关的 `mastered_words`。`AnnotatorService` 随后只构造一份
基础 Context，所有 chunk 共用完全相同的 system blocks 和章节级熟词 JSON。每个模型请求只在最后追加
自己的 `reader_text`：

```text
chunk_0 request = shared_base_context + reader_text(chunk_0)
chunk_1 request = shared_base_context + reader_text(chunk_1)
chunk_2 request = shared_base_context + reader_text(chunk_2)
```

这种“固定内容在前、变动内容在后”的排列为 Provider 的 prompt caching 提供稳定前缀；是否实际命中缓存
仍取决于所用 Provider 和模型。请求中不应在 `reader_text` 之前插入 chunk 索引、进度或其他
会逐块变化的数据。

`selection_policy` 不是每个系列都必须实现的模板。`corpus/catalog.yaml` 只有在某个系列确实需要
稳定的额外选词边界时才配置 `selection_policy_id`；没有配置时，英文 Profile 不插入空 block，
也不会附加任何题材说明。

## AnnotatorService 的两层兜底

译注以单个 chunk 为独立模型任务。每个 chunk 的处理流程如下：

```text
单个 chunk
    ↓
Provider 调用与 retry
    ├── 最终失败 → 原文回退，provider 类警告
    └── 返回内容
            ↓
        基础可用性检查
            ├── 空输出或截断 → 原文回退，validation 类警告
            └── 其他非空输出 → 使用译注
```

第一层由 Provider 提供，解决网络超时、限流和临时服务错误。重试耗尽后，Service 不让一个
chunk 阻断整章，而是使用该 chunk 的原文，并生成：

```text
category = provider
code = provider_failed
```

第二层只检查输出是否为空或因 token 上限截断，并生成 `validation` 类问题：

```text
empty_output
truncated_output
```

Profile 仍保留格式与原文还原校验器，供测试或离线诊断使用，但它不再作为阅读主链路的
强制闸门。整段生成模型对空行、引号或标点的轻微调整会被直接接受，不会导致 chunk 回退。

降级信息使用 `contracts/annotation.py` 中的 `ServiceIssue`、`AnnotationChunkOutcome` 和
`AnnotationResult` 传递。Service 同时发送 `annotation.degraded` 事件，事件包含稳定的
`category`、`code` 和 `chunk_index`；前端不应依赖可变的错误文案判断类型。

## 已掌握词动态筛选

已掌握词不会再整表加载并复制到每个 Prompt。Dispatcher 在 Provider 并发开始前先对整章做
一次轻量候选提取，再通过 `VocabularyRepository.find_mastered_words()` 批量查询当前语言
下真正出现在本章的已掌握词：

```text
整章原文
    → 提取英文单词/短语与中文短片段
    → 分批查询 SQLite（每批最多 400 个候选）
    → 得到本章相关已掌握词
    → AnnotatorService 为整章构造一份基础 Context
    → 所有 chunk 共用本章相关 mastered_words
    → 并发调用 Provider
```

SQLite 查询不进入并发 chunk 区域，因此不会让 8 个模型任务争用数据库锁。行为日志中的
`annotation_mastery_prepared` 记录候选数、命中数和准备耗时，便于用真实章节评估本地筛选成本。
候选器是检索用途的轻量规则，不承担完整语言学分词：当前支持最多四个英文词的连续短语，以及
最多四个连续中文字符的片段。当前单章最多约 8 个 chunk，因此不再为每个 chunk 重复提取和
筛选；若真实日志显示单章命中规模显著增长，再评估恢复更细粒度的筛选。

## 合并与持久化

- 校验通过和降级后的 chunk 都按原始 `index` 合并，因此前端始终能获得完整可读文本。
- 部分 chunk 降级时，Dispatcher 可以保存混合译注，并把完成状态标为 `degraded`。
- 全部 chunk 降级时，只向前端返回原文，不创建译注副本，也不标记为已译注，便于用户稍后重试。
- 取消请求和未分类的程序异常不属于业务降级，仍然向上抛出，并取消、等待其余并行任务退出。

这里的原则是：模型或格式问题不能破坏阅读体验，但程序错误也不能被宽泛异常捕获静默隐藏。
