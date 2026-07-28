# 阅读伴侣的已读内容检索

本文定义阅读伴侣第一批“阅读历史”工具的职责、可信范围和返回边界。当前已完成 Contract、
Port、可信范围构建器、两个检索 Service 与词汇历史 SQLite Adapter，尚未注册 Agent Tool。

## 1. 目标

阅读伴侣需要回答两类问题：

1. “这个人物以前出现过吗？”——回查本书此前已经完整读完的章节；
2. “这个词我是不是见过？”——回查生词本里保存的既往语境。

两类检索都只能提供证据。如何解释人物、事件或词义差别，仍由 Agent 根据工具结果完成。

## 2. 共享的可信范围

两个工具共享 `PreviousReadingScope`：

```text
当前阅读位置
    + ChapterReadingCheckpointRepository
    + Corpus 单元归属
            ↓
PreviousReadingScope
    ├── 当前 book_id
    ├── 当前 chapter_id / chapter_no
    └── 此前完整读完章节及其 unit_ids
```

范围由 Application 根据真实阅读状态生成，不由模型提供。只有满足以下条件的内容可以进入范围：

- 属于当前图书；
- 存在完整章节阅读检查点；
- 章节号严格小于当前章节；
- Corpus 中的阅读单元确实属于该章节。

`PreviousReadingScopeBuilder` 使用当前 Corpus 作为章节结构真相，并与历史检查点的 `unit_ids`
求安全交集。只有检查点恰好覆盖当前 Corpus 中该章的全部 section 时才接纳；缺少 section、
包含失效 unit 或章节元数据不一致的旧检查点会被排除。

当前章节整体排除，即使用户已经读到该章末尾，也不按页面位置裁切后加入检索。当前正在阅读的
章节、页面和选中文本应作为 Invocation Context 直接提供给 Agent。

`AgentToolExecutionContext` 将这份可信范围与 `session_id`、`episode_id` 一起传给 Tool。它与
模型生成的工具参数分离，因此模型不能伪造 `book_id`、章节号或可访问的 `unit_id`。

## 3. `search_previous_chapters`

用途：在当前图书此前完整读完的章节中，查找人物、事件和情节依据。

模型参数保持窄小：

```json
{
  "query": "Snape",
  "max_chapters": 4
}
```

Application 内部把模型参数与可信范围组合为 `PreviousChapterSearchRequest`。检索过程可以同时
使用 Corpus 的章节摘要和少量原文，但结果必须按章节组织：

```text
PreviousChapterMatch
├── chapter_id / chapter_no / chapter_title
├── summary
└── excerpts[]
    ├── unit_id
    └── text
```

规则：

- 摘要用于人物关系、事件概览和阅读恢复；
- 原文摘录用于具体措辞、动作或对话依据；
- 默认读取原始 Corpus，不读取模型译注副本；
- 同一阅读单元可以返回多个相关摘录；
- 结果按章节时间顺序返回，并受 `max_chapters` 限制；
- 每个结果都必须再次通过 Contract 校验，不能越过可信范围。

第一版可以采用关键词匹配，不必引入向量库。后续只有在真实问题证明关键词召回不足时，再替换
检索实现；Tool Contract 不需要因此改变。

当前 `PreviousChapterSearchService` 已采用以下轻量策略：

- 模型应传入简短人物名或事件短语，而不是完整问题；
- 英文短词按单词边界匹配，避免 `he` 命中 `the`；
- 摘要命中获得更高权重，原文按 Markdown 空行划分为候选段落；
- 每章默认最多返回两段、每段最多 500 字符；
- 先按匹配强度选取 `max_chapters` 个章节，再按章节顺序返回；
- 执行前再次核对 Scope 与当前 Corpus；不一致时返回稳定的 `scope_stale` 错误。

## 4. `search_vocabulary_history`

用途：从生词本中查找同一词在此前章节保存过的语境，供 Agent 比较不同语义和用法。

模型参数：

```json
{
  "word": "charge",
  "max_encounters": 5
}
```

`language_id`、`book_id` 和可访问的 `unit_id` 仍由后端提供。Application 先按现有词汇规则对
查询词做规范化，再通过 `VocabularyHistoryRepository` 精确查找同一 `normalized_word`：

```text
VocabularyEncounter
├── book / chapter / unit 来源
├── word / normalized_word / pos
├── translation
├── context
├── encounter_count
└── mastered
```

规则：

- 第一版只查当前图书，不跨书聚合；
- 只返回此前完整读完章节中的记录；
- 这是生词语境检索，不是普通词典查询；
- 第一版只做精确规范词匹配，不进行词形还原或模糊匹配；
- Tool 返回保存的事实，Agent 负责解释各语境中的词义差别；
- 超过预算时选取最近的若干语境，再按章节顺序返回；
- 没有 context 的词条不参与用法比较；
- 当前存储在同一 unit 内只保留一个代表性语境并累计次数，因此第一版主要比较跨 unit、跨章节
  的语境。

虽然自动译注可能在用户读完章节前就写入 `unit_vocabulary`，但工具必须使用相同的
`PreviousReadingScope` 再过滤一次，避免把尚未读过的词汇记录暴露给 Agent。

## 5. 分层与职责

```text
Reading Companion Agent
        ↓ 模型工具调用
ToolRegistry
        ↓ 注入 AgentToolExecutionContext
Retrieval Tool
        ↓
Application Search Service
    ├── PreviousReadingScope Builder
    ├── ChapterReadingCheckpointRepository
    ├── CorpusStore
    └── VocabularyHistoryRepository
            ↓
      SQLite Adapter（词汇历史）
```

- Contract：定义可信范围、请求、结果和越界校验；
- Tool：把 JSON 参数转成应用请求，把结果转成模型可读 JSON；
- Application Service：执行规范化、搜索、预算裁切和结果组装；
- Repository Port：声明读取生词历史需要的能力；
- Storage Adapter：执行 SQL，不向 Agent 暴露表结构；
- Agent：决定何时检索，并根据证据组织自然语言回答。

Tool 不直接读取文件路径或执行 SQL；Repository 不生成面向模型的回答；Agent 不决定数据访问
范围。

## 6. 空结果与错误

“没有找到”是正常结果：

```json
{
  "ok": true,
  "found": false,
  "matches": []
}
```

可恢复错误使用稳定错误码，例如：

- `no_active_reading`：当前没有可确定的阅读位置；
- `no_completed_history`：尚无此前完整读完章节；
- `invalid_query`：查询为空或参数超限；
- `scope_stale`：执行时阅读范围已失效；
- `corpus_unavailable`：原始语料暂不可读；
- `vocabulary_history_unavailable`：生词历史暂不可读。

工具结果不包含文件路径、SQL、异常堆栈或未来章节信息。可恢复错误交给 Agent 用自然语言说明，
不应让整个对话 Loop 崩溃。

## 7. 实现顺序

1. 已完成：共享 Scope、两个查询结果 Contract 和越界测试；
2. 已完成：只读 `VocabularyHistoryRepository` Port；
3. 已完成：基于 Corpus 与完整章节检查点的 `PreviousReadingScopeBuilder`；
4. 已完成：摘要与原文段落的此前章节检索 Application Service；
5. 已完成：SQLite 词汇历史 Adapter 与词汇检索 Application Service；
6. 下一步：把两个 Tool 注册进现有 `ToolRegistry`，再接入 Agent 提示词和端到端测试。

按这个顺序可以先证明无剧透边界，再接入真实检索；不会让 Agent Loop、Corpus 和 SQLite 在同一
步中一起变化。
