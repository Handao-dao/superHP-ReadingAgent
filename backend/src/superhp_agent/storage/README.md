# Storage 与内容存储规划

本文定义后端各类数据的唯一真相来源，以及 Store、Repository、Artifact 和日志之间的边界。
目标是避免同一状态同时由 Markdown、JSON 和 SQLite 维护，导致读取结果漂移。

项目整体分层见 [`../README.md`](../README.md)，当前功能和配置见
[`BACKEND_OVERVIEW.md`](../../../BACKEND_OVERVIEW.md)。

## 核心原则

```text
文件       保存长文本内容和生成产物
SQLite     保存可查询、可变、有关联的应用数据
JSONL      保存追加式诊断和审计事件
```

每项应用状态只能有一个权威来源。其他位置如果保留相同信息，只能作为可删除、可重建的索引，
不能参与互相覆盖的双向同步。

## 唯一真相来源

| 数据 | 权威来源 | 访问边界 | 是否可重建 |
| --- | --- | --- | --- |
| 小说和文言文原文 | `corpus/` Markdown | `CorpusStore` | 否，属于源内容 |
| 标注版本正文 | `backend/data/annotated_corpus/` Markdown | `AnnotatedCopyStore` | 是，可重新调用模型生成 |
| 阅读单元关系索引 | SQLite `units` | 内部 Unit Repository | 是，可从 Corpus 重新同步 |
| 语言级词元 | SQLite `lexemes` | `VocabularyRepository` | 可从书籍词表重建 |
| 全局掌握状态 | SQLite `lexeme_mastery` | `VocabularyRepository` | 否，属于用户数据 |
| 每本书的词表 | SQLite `book_vocabulary` | `VocabularyRepository` | 可从有效标注副本重新索引 |
| 单词在章节中的出现 | SQLite `unit_vocabulary` | `VocabularyRepository` | 可从有效标注副本重新索引 |
| 书签 | SQLite `bookmarks` | `BookmarkRepository` | 否，属于用户数据 |
| 当前章节和阅读进度 | 目标为 SQLite | `ReadingProgressRepository` | 否，属于用户状态 |
| 选书候选与蓝思区间 | SQLite `recommendation_catalog` | `BookDifficultyCatalog` | 是，可从导入数据重建 |
| 选书 Agent 对话 | SQLite `recommendation_sessions` | `RecommendationSessionRepository` | 否，属于进行中的用户对话 |
| 用户主动查词事实 | SQLite `reading_lookup_events` | `ReadingLookupRepository` | 否，属于阅读行为 |
| 每本书的译注支持目标 | SQLite `book_reading_support` | `ReadingSupportRepository` | 否，属于阅读适配状态 |
| 完整章节阅读快照 | SQLite `chapter_reading_checkpoints` | `ChapterReadingCheckpointRepository` | 否，属于已冻结的阅读事实 |
| 困难提示、用户选择与冷却 | SQLite `reading_difficulty_prompts` | `ReadingDifficultyPromptRepository` | 否，属于用户授权状态 |
| 行为历史 | `events.jsonl` | `EventLogStore` | 不参与当前状态计算 |

## 原文：CorpusStore

`corpus/` 中的 Markdown 是原文和阅读单元元数据的唯一权威来源：

- YAML frontmatter 保存 `unit_id`、书籍、章节、Profile 等元数据。
- Markdown body 保存原文。
- 应用运行时只读，不把正文复制进 SQLite。
- `CorpusStore` 是从 `unit_id` 到安全文件路径的唯一映射入口。

SQLite `units` 只为 vocabulary、bookmark 等关系数据提供元数据索引和稳定引用。它不是正文仓库，
数据库被删除后可以重新扫描 Corpus 建立。

## 标注版本：AnnotatedCopyStore

标注版本是完整长文本和可导出的生成产物，继续使用 Markdown 文件保存，不把正文重复写入 SQLite。
每个阅读单元只保留一份标注副本，文件名由 `unit_id` 确定，例如：

```text
hp01-ch01.annotated.md
```

标注文件 frontmatter 当前记录：

```yaml
source_unit_id: hp01-ch01
source_hash: <sha256>
profile_id: english_novel
annotation_format_version: 1
annotation_target: 8      # 仅英文译注记录本次实际使用值
status: completed        # 或 degraded
validated_chunk_count: 4
total_chunk_count: 5
annotated_at: <UTC timestamp>
```

`source_hash` 用于发现原文修改后已经过期的译注。`status` 和 chunk 计数用于说明混合降级结果，
`annotation_target` 用于追溯生成该副本时采用的支持强度；但“译注是否存在”仍以文件实际存在为准，
不在 Memory 或 SQLite 维护第二份布尔状态。

文件写入使用同目录临时文件加原子替换。标注文件是权威生成产物；SQLite 中的 vocabulary encounter
只是可重建查询索引，因此不要求伪造跨文件系统和 SQLite 的事务。

## 单词：书籍隔离与语言级共享

词义和词性按书籍隔离，掌握状态按语言共享：

```text
lexemes
    language_id + normalized_word，保存语言级词汇身份

lexeme_mastery
    关联 lexeme，保存跨书共享的 mastered 状态

book_vocabulary
    book_id + lexeme_id，保存当前书中的翻译、词性和 Profile

unit_vocabulary
    unit 与 book_vocabulary 的关联、上下文翻译、例句和出现次数
```

核心唯一约束为：

```sql
UNIQUE(language_id, normalized_word)  -- lexemes
UNIQUE(book_id, lexeme_id)            -- book_vocabulary
```

例如 HP1 与 HP2 中的 `wand` 各自拥有书籍词条，可以保留不同翻译和统计，但都指向同一个
`(en, wand)` lexeme；任意一本书把它标为掌握后，两本书都会显示为已掌握。不同语言中的同形词
不会共享状态。`normalized_word` 使用去除首尾空白后的 Unicode `casefold` 结果。

当前数据均为测试数据，本次重构直接重置旧 SQLite 与译注产物，不保留旧 `vocabulary` schema
的兼容迁移。

## 选书目录：BookDifficultyCatalog

推荐候选统一保存在 SQLite `recommendation_catalog`，不再额外维护 YAML 难度目录。第一版面向
设计验证，默认数据库中的候选均可直接阅读，只保存：

```text
中英文书名
作者（可空）
单本 / 系列 / 合集类型
蓝思最小值与最大值
内容题材列表
原始导入文本
```

精确蓝思值使用相同的最小值和最大值；系列范围分别保存上下限。`BookDifficultyCatalog` 负责按
稳定 id、重叠蓝思区间和题材查询，Agent 不直接访问 SQLite 或生成任意 SQL。目录数据可以由
一次性导入器重建，因此不属于不可丢失的用户状态。

## 选书对话：RecommendationSessionRepository

推荐 Loop 可以在自然语言提问后暂停，因此 SQLite 需要保存下一次调用所需的完整 Session：

```text
session_id
phase
request
真实 user / assistant / tool 消息
tool_call_count
observed_catalog_ids
```

`recommendation_sessions` 使用 `session_id` 作为主键，把 `phase` 保留为可查询列，并将完整
Session 作为带版本号的 JSON 聚合保存。JSON 中保留 Assistant Tool Call、原始参数和配对的
`tool_call_id`，恢复后可以直接重建 Provider 上下文，不使用容易丢失信息的对话摘要。

Application 层的 `RecommendationAgentRunner` 负责“加载 → 运行 Loop → 保存”；Agent 不依赖
Repository，SQLite Adapter 也不理解模型决策。当前不建设事件溯源、逐消息表、分支会话或
compaction，等真实会话规模产生压力后再评估。

## 书签：BookmarkRepository

书签属于不可重建的用户数据，以 SQLite 为唯一来源。`body_kind` 继续区分原文和译注。

`page_index` 和 `progress_ratio` 受窗口、字体和分页算法影响，只作为最后的恢复回退。当前稳定定位顺序为：

- `excerpt`：优先匹配附近文本锚点。
- `paragraph_index`：文本未匹配时使用内容块位置。

恢复时优先使用内容锚点，最后才回退到页码或比例。

## 阅读进度：ReadingProgressRepository

生产运行时现在以 SQLite 为 current/opened/read 状态的唯一来源。旧
`reading_memory.json`、JSON Memory 实现和一次性导入逻辑均已移除。

当前结构为：

```text
reading_state
    id = 1
    current_unit_id
    last_opened_at

unit_progress
    unit_id
    opened_at
    read_at
```

其中：

- 当前章节来自 `reading_state`。
- 是否已读来自 `unit_progress.read_at`。
- 是否存在译注来自 `AnnotatedCopyStore`，不保存 `annotated_unit_ids`。
- `units` 只保留 Corpus 元数据，不保存可变阅读状态。

新 schema 不再创建 `units.status/read_at/annotated_at/annotated_path`。旧数据库中已存在的冗余列
保持原样，但不会再被运行时读取或写入。

## 行为日志：EventLogStore

`EventLogStore` 把 `events.jsonl` 作为追加式诊断记录，适合调试和审计。它不参与当前 Cards、
阅读状态或译注存在性计算，也不用于重建用户状态。只有出现复杂查询需求时，才考虑迁入独立
SQLite events 表。

## Store 与 Repository 命名

```text
CorpusStore
    读取只读源内容文件

AnnotatedCopyStore
    读写完整生成型 Artifact

VocabularyRepository
    查询和更新关系型单词数据

VocabularyHistoryRepository
    在可信阅读范围内只读查询同一词的既往语境

BookmarkRepository
    查询和更新关系型书签数据

ReadingProgressRepository
    查询和更新关系型阅读状态

BookDifficultyCatalog
    查询本地选书候选和蓝思区间

RecommendationSessionRepository
    保存和恢复完整选书 Agent 会话

ReadingLookupRepository
    记录成功查词，并按明确的阅读单元集合聚合次数

ReadingSupportRepository
    保存每本书当前每 300 词的译注支持目标

ChapterReadingCheckpointRepository
    保存每个完整章节首次读完时的不可变观察快照

ReadingDifficultyPromptRepository
    保存每本书最近一次困难提示、用户选择、提示冷却和推荐会话关联

EventLogStore
    追加诊断事件
```

Store 面向文件内容或追加型记录；Repository 面向可查询、可更新的领域记录。统一存储边界不等于
把所有能力都命名为 Repository，也不等于把所有正文都塞进 SQLite。

`reading_lookup_events` 与 `events.jsonl` 的职责不同：前者是后续 Reading Monitor 计算查词
密度的业务事实，保存 `unit_id/chapter_id/book_id`、归一化词项、是否已有译注以及时间；后者
仍只是诊断日志。查词 Provider 失败不写业务事实，监控存储失败也不能中断已经成功的查词响应。

`book_reading_support` 按 `book_id` 隔离英文译注目标。没有显式记录时，
`ReadingSupportRepository` 返回默认值 8，不为一次读取创建冗余行。Dispatcher 在生成英文译注前
读取该值并传给 Context Builder；文言文链路不使用它。修改目标只影响之后新生成的译注，不会自动
重写已经存在的副本；自动升降仍由后续 `ReadingAdaptationPolicy` 决定。

`chapter_reading_checkpoints` 以 `book_id + chapter_id` 保证幂等。只有同一章节下全部
`unit_id` 已读时才记录，内容包括章节词数、查词总数、已有译注词查词数以及各 section 共同使用的
实际 `annotation_target`。缺少译注副本或 section 目标不一致时，目标诚实记录为 `NULL`。
历史 checkpoint 不删除；`ReadingAdaptationEvaluator` 按 `book_id` 只读取最近三个组成滑动
窗口。`book_reading_support` 同时保存每本书的最后评估章节、连续窗口计数和三章调整冷却。
`INCREASE/DECREASE` 会把新目标、评估位置、streak 与冷却作为同一份状态写回；
`HOLD/DIFFICULTY_ALERT` 不改变目标。已有译注副本不会被自动重写。

`reading_difficulty_prompts` 与 `book_reading_support` 刻意分开：前者保存用户看到并操作的授权
状态，后者保存自动译注策略状态。`difficulty_alert` 产生时保存最近三章的聚合证据；选择继续后
按新的 `chapter_id` 扣减三章冷却，同一章重复完成不重复扣减；选择换书后保存对应的
`recommendation_session_id`。页面或 WebSocket 重连后可以重新读取仍为 `pending` 的提示。

## 渐进迁移顺序

1. （已完成）为 `AnnotatedCopyStore` 增加原子写入和 `source_hash/status/chunk counts` 元数据。
2. （已完成）从 Reading Memory 中移除 `annotated_unit_ids`，译注存在性只由文件系统判断。
3. （已完成）新建 `ReadingProgressRepository`，把 current/opened/read 状态迁入 SQLite。
4. （已完成）保留 JSONL 日志，移除 `reading_memory.json` 的运行时依赖。
5. （已替代）早期曾按 `profile_id + normalized_word` 隔离 vocabulary；当前已升级为书籍词表隔离与语言级 Mastery 共享。
6. （已完成）为 bookmarks 增加译注 level 和更稳定的文本定位字段。
7. （已完成）停止在新 schema 中创建 `units` 的未使用运行状态字段；旧数据库中的冗余列可兼容保留，
   不需要为删除空列执行高风险表重建。
8. （已完成）新增 `ReadingSupportRepository`，按书持久化英文译注支持目标，并把生成时使用值写入
   译注副本元数据。
9. （已完成）新增章节阅读 checkpoint，在完整章节首次读完时冻结后续增量观察需要的事实。

每一步都先建立新读取路径和兼容迁移，再移除旧来源，避免同一状态长期双写。
