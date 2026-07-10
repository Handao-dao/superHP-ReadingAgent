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
| 单词和掌握状态 | SQLite `vocabulary` | `VocabularyRepository` | 掌握状态不可重建 |
| 单词在章节中的出现 | SQLite `unit_vocabulary` | `VocabularyRepository` | 可从有效标注副本重新索引 |
| 书签 | SQLite `bookmarks` | `BookmarkRepository` | 否，属于用户数据 |
| 当前章节和阅读进度 | 目标为 SQLite | `ReadingProgressRepository` | 否，属于用户状态 |
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
文件名由 `unit_id + level` 确定，例如：

```text
hp01-ch01.intermediate.annotated.md
```

标注文件 frontmatter 当前记录：

```yaml
source_unit_id: hp01-ch01
source_hash: <sha256>
profile_id: english_novel
level: intermediate
annotation_format_version: 1
status: completed        # 或 degraded
validated_chunk_count: 4
total_chunk_count: 5
annotated_at: <UTC timestamp>
```

`source_hash` 用于发现原文修改后已经过期的译注。`status` 和 chunk 计数用于说明混合降级结果，
但“译注是否存在”仍以文件实际存在为准，不在 Memory 或 SQLite 维护第二份布尔状态。

文件写入使用同目录临时文件加原子替换。标注文件是权威生成产物；SQLite 中的 vocabulary encounter
只是可重建查询索引，因此不要求伪造跨文件系统和 SQLite 的事务。

## 单词：VocabularyRepository

单词适合 SQLite，因为它需要去重、筛选、统计、掌握状态和章节关联。当前两表方向保留：

```text
vocabulary
    单词主体、Profile 作用域、标准化词形、词性和掌握状态

unit_vocabulary
    unit 与单词的关联、上下文翻译、例句和出现次数
```

当前唯一约束已经从全局 `UNIQUE(word)` 演进为：

```sql
UNIQUE(profile_id, normalized_word)
```

`normalized_word` 使用去除首尾空白后的 Unicode `casefold` 结果。这样不同 Profile 不会错误共享
翻译、词性和掌握状态，同一 Profile 内的大小写变体仍指向同一记录。旧全局词条会在 schema
升级时按关联 unit 的 Profile 拆分并重新关联；`unit_vocabulary` 继续保留上下文相关翻译。

## 书签：BookmarkRepository

书签属于不可重建的用户数据，以 SQLite 为唯一来源。当前 `body_kind` 需要继续区分原文和译注；
存在多个译注 level 时，通过 `annotation_level` 保存对应的 artifact variant。

`page_index` 和 `progress_ratio` 受窗口、字体和分页算法影响，只作为最后的恢复回退。当前稳定定位顺序为：

- `excerpt`：优先匹配附近文本锚点。
- `paragraph_index`：文本未匹配时使用内容块位置。
- `annotation_level`：打开书签所对应的译注版本。

恢复时优先使用内容锚点，最后才回退到页码或比例。

## 阅读进度：ReadingProgressRepository

生产运行时现在以 SQLite 为 current/opened/read 状态的唯一来源。旧 `reading_memory.json` 已从
应用启动和日常读写链路移除；`memory.py` 只暂时保留为离线迁移与兼容测试模块。

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

BookmarkRepository
    查询和更新关系型书签数据

ReadingProgressRepository
    查询和更新关系型阅读状态

EventLogStore
    追加诊断事件
```

Store 面向文件内容或追加型记录；Repository 面向可查询、可更新的领域记录。统一存储边界不等于
把所有能力都命名为 Repository，也不等于把所有正文都塞进 SQLite。

## 渐进迁移顺序

1. （已完成）为 `AnnotatedCopyStore` 增加原子写入和 `source_hash/status/chunk counts` 元数据。
2. （已完成）从 Reading Memory 中移除 `annotated_unit_ids`，译注存在性只由文件系统判断。
3. （已完成）新建 `ReadingProgressRepository`，把 current/opened/read 状态迁入 SQLite。
4. （已完成）保留 JSONL 日志，移除 `reading_memory.json` 的运行时依赖。
5. （已完成）为 vocabulary 增加 `profile_id + normalized_word` 作用域。
6. （已完成）为 bookmarks 增加译注 level 和更稳定的文本定位字段。
7. （已完成）停止在新 schema 中创建 `units` 的未使用运行状态字段；旧数据库中的冗余列可兼容保留，
   不需要为删除空列执行高风险表重建。

每一步都先建立新读取路径和兼容迁移，再移除旧来源，避免同一状态长期双写。
