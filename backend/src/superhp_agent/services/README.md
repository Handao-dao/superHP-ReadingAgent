# Service 层说明

本文记录 `services/` 内业务服务的职责边界和运行语义。项目整体分层见上一级
[`README.md`](../README.md)，后端功能总览见 [`BACKEND_OVERVIEW.md`](../../../BACKEND_OVERVIEW.md)。

## 职责边界

Service 负责完成一个明确的后端业务任务，例如译注生成、上下文查词和推荐候选匹配。它可以组合
Profile、Context 和 Provider Port，但不负责：

- 接收 HTTP 或 WebSocket 消息。
- 决定阅读流程和前端 Cards。
- 直接操作 SQLite、Memory 或译注文件。
- 把模型返回错误直接拼成 Transport 协议。

Provider 负责模型 SDK、请求参数和瞬时错误重试；Service 负责判断最终模型结果在当前业务中
是否可用，并以 Contracts 中的结构化结果向上层传递状态。

## RecommendationCandidateService 的严格匹配

`RecommendationCandidateService` 依赖 `BookDifficultyCatalog` Port，负责对本地图书候选做
第二次边界校验、去重和排序。第一版严格保持调用方给出的条件：

- 蓝思区间必须与候选区间重叠；
- 指定题材时，候选至少匹配其中一个标签；
- 指定单本、系列或合集类型时，不返回其他类型；
- 明确排除的目录 id 不参与排序；
- 优先匹配更多题材标签，其次选择更接近目标区间中心的候选；
- 无结果时返回空的 `BookCandidateMatchResult`，不自行扩大蓝思区间或删除题材条件。

Agent 使用的 `BookCatalogSearchTool` 位于 `agent_tools/`。它只做参数规范化和结果序列化；
“下一次是否放宽条件”由 Agent 在看到 Tool Result 后决定，不能隐藏在 Service 或 SQLite
Adapter 中。

## 英文译注 Context 组织

英文小说是当前产品主路径。译注 Context 按“稳定规则 → 整章任务数据 → 当前 chunk”
的顺序组织：

```text
System / Stable
    system_policy
    annotation_contract
    selection_policy（可选的系列补充）
    annotation_examples
    mastered_words_policy
    output_contract

System / Reading Support
    annotation_support（当前每 300 词的支持上限）

User / Chapter Task
    mastered_words

User / Chunk Data
    reader_text
```

各 block 的职责如下：

- `system_policy`：定义英文词汇译注任务、目标读者和选词优先级，不再硬编码密度。
- `annotation_contract`：定义 marker 格式、POS、原文还原不变式和释义质量。
- `selection_policy`：可选的系列特色补充；普通英文小说不生成此 block。当前仅哈利波特系列使用，其他小说直接采用通用规则。
- `annotation_examples`：演示单词、完整短语和错误重复替换。
- `mastered_words_policy`：解释熟词排除以及熟词作为更长表达组成部分时的边界。
- `output_contract`：约束响应外壳，并明确零标注时原样返回输入。
- `annotation_support`：携带当前每 300 词的译注支持上限；它是可少用的 ceiling，不是必须凑满的 quota。

英文译注不再按高、中、低三套固定模板分级，统一以 B1–B2 读者为参考。当前默认
`annotation_target` 为每 300 词 8 处，调用方可以在 1～20 之间显式传入新的支持目标；模型可以
少用，但不能为了填满目标加入弱相关标注。当前步骤只建立 Context 参数入口，尚未持久化每本书
的目标，也不会根据 Reading Monitor 自动调整。Prompt 仍要求模型尽量保持原文，但阅读主链路
不再使用逐字符一致性作为整块成功与否的判定条件。

标注边界以单词为优先；只有固定搭配、习语或拆开后会丢失、误解整体含义的特殊表达，才整体标注为 phrase。

### 整章复用与 prompt caching

Dispatcher 在并发译注前一次性准备整章相关的 `mastered_words`。`AnnotatorService` 随后只构造一份
基础 Context，所有 chunk 共用完全相同的 system blocks、当前 `annotation_support` 和章节级熟词
JSON。每个模型请求只在最后追加自己的 `reader_text`：

```text
chunk_0 request = shared_base_context + reader_text(chunk_0)
chunk_1 request = shared_base_context + reader_text(chunk_1)
chunk_2 request = shared_base_context + reader_text(chunk_2)
```

`annotation_support` 位于固定 System Blocks 末尾：当阅读情况改变目标时，前面的合同、示例和
可选系列规则仍构成稳定缓存前缀；同一章的所有 chunk 又共享同一个支持目标。是否实际命中缓存仍
取决于所用 Provider 和模型。请求中不应在 `reader_text` 之前插入 chunk 索引、进度或其他会逐块
变化的数据。

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
