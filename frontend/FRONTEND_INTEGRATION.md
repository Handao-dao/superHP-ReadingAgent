# 前端集成说明

本文记录当前前端阅读界面以及前后端对接契约。后端内部的 Provider、Service、Repository、
Storage 和 Dispatcher 分层不在这里展开；前端 `src/` 的组件边界与依赖方向见
[`src/README.md`](src/README.md)。

## 当前产品形态

前端是受控阅读界面，而不是自由聊天页。主要职责是：

- 按阅读场景和系列浏览书库。
- 展示原文或后端生成的译注副本。
- 渲染后端下发的 guided cards，并把用户选择作为 action 发回后端。
- 展示译注进度、模型重试、降级和失败状态。
- 提供上下文查词、手动加词、生词复习和显式书签。

当前主路径是英文小说阅读；文言文 Profile 是迁移扩展点。英文书库现包含 Harry Potter 和
Agatha Christie · Selected Mysteries 两个 collection。

## 页面与模块边界

页面由 [`App.vue`](src/App.vue) 协调，主要模块如下：

```text
App.vue
├── useReadingCatalog      Profile、collection、book、chapter 目录
├── useReadingSocket       WebSocket 会话、cards、正文和模型状态
├── useReaderPagination    CSS columns 分页与页面导航
├── useBookmarks           书签读取、保存、删除和定位
├── useWordLookup          点击查词与手动词汇操作
├── ReadingSidebar         collection → book → chapter 三级目录
├── ReadingTopbar          阅读/生词表切换与纸张主题
├── ReadingTextPage        当前正文页
├── GuidancePanel          章节 summary 和 guided cards
├── ReaderStatePage        空白、生成中和错误状态
├── ReadingPaperFooter     body mode、书签按钮和页码
├── LookupPopover          查词结果与添加/取消标注操作
└── VocabularyPanel        生词表查询与掌握状态管理
```

组件负责展示和发出用户意图；API 请求、WebSocket、持久化状态和跨模块协调留在 composable
或 `App.vue` 中。

## 阅读界面

- 桌面端是左侧书库目录和中央阅读纸张；移动端目录变为抽屉。
- 目录按 `collection → book → chapter` 逐级进入，并在当前层级内搜索。
- 后端 catalog 不可用时，前端仍会按章节中的 `book_id` 自动整理到 `Other Books/其他选篇`。
- 正文使用固定窗口和 CSS columns 分页；方向键、空格和页面按钮负责翻页。
- 正文最后一页之后进入 guidance 页，展示 summary 和后端 cards。
- 译注生成期间保留章节上下文，只在纸张内显示进度，不预览未合并的 chunk。
- 纸张主题支持 `parchment` 和 `white-paper`，只影响显示，不进入后端请求。
- 英文正文的普通单词和现有译注词可以点击查词；当前不支持用户框选任意短语查词。

当前页面状态可以概括为：

```ts
type ReaderMode = "empty" | "reading" | "guidance" | "generating" | "error"

type ReadingLoadStatus =
  | "connecting"
  | "offline"
  | "idle"
  | "loading_unit"
  | "generating_annotation"
  | "model_retrying"
  | "failed"
  | "completed"
```

前端保留两个兼容状态分支 `json_repairing` 和 `annotation.not_ready`，但当前后端主链路不再发送
对应事件。

## 本地状态

前端使用以下 `localStorage` key：

| key | 用途 |
| --- | --- |
| `superhp_profile_id` | 当前阅读 Profile |
| `superhp_current_unit_id` | 当前阅读单元，用于刷新后恢复章节/cards 上下文 |
| `superhp_reader_theme` | `parchment` 或 `white-paper` |

页面位置不自动持久化。精确阅读定位由用户显式保存书签完成。

## HTTP API

### 健康与目录

#### `GET /api/health`

返回 `{ "status": "ok" }`。

#### `GET /api/profiles`

返回可用 Profile：

```ts
type ProfileMeta = {
  id: string
  language_id: string
  label: string
  renderer_hint: string
  is_default: boolean
}
```

前端使用 `renderer_hint` 选择 English Novel 或 Classical Chinese renderer。

#### `GET /api/library`

可选查询参数：`profile_id`。

返回 collection 和稳定的图书顺序：

```ts
type LibraryCollectionMeta = {
  id: string
  profile_id: string
  title: string
  author: string
  order: number
  books: Array<{ id: string; order: number }>
}
```

Catalog 只提供层级和顺序；书名、章节和阅读状态由 `/api/units` 返回的数据补齐。

#### `GET /api/units`

可选查询参数：`profile_id`。返回 `ReadingUnitMeta[]`。

#### `GET /api/units/{unit_id}`

直接读取一个原文单元，主要用于调试或 HTTP 兜底。常规阅读通过 WebSocket action 打开正文。

`/api/chapters` 和 `/api/chapters/{chapter_id}` 是旧命名兼容入口。

### 查词与词表

#### `POST /api/word-lookup`

请求：

```json
{
  "word": "conviction",
  "sentence": "I said it with conviction.",
  "profile_id": "english_novel"
}
```

返回：

```ts
type WordLookupResult = {
  word: string
  word_cn: string
  pos: string
  sentence_cn: string
}
```

英文查词是通用小说上下文查词，不绑定某个系列。后端要求 `word_cn` 非空；请求带句子时也要求
`sentence_cn` 非空。格式或必需字段不合规时，Lookup Service 会执行内容重试。

#### `GET /api/vocabulary`

可选查询参数：

- `unit_id`
- `chapter_id`
- `profile_id`
- `book_id`

书中生词按 `book_id` 隔离；同一语言下的“已掌握”状态全局共享。

#### `POST /api/vocabulary`

把查词结果作为手动词条写入当前阅读单元：

```json
{
  "word": "conviction",
  "translation": "确信",
  "context": "I said it with conviction.",
  "pos": "noun",
  "unit_id": "ac08-ch17"
}
```

写入成功后，前端使用 `manualAnnotations` 立即重绘正文，无需重新生成整章译注。

#### `PATCH /api/vocabulary/{vocab_id}/master`

按词条 id 标记掌握或重新学习。

#### `POST /api/vocabulary/mark-by-word`

按 `word + profile_id` 更新语言级掌握状态，当前用于从阅读正文取消标注。

#### `DELETE /api/vocabulary/{vocab_id}`

删除一个书中词条，不等同于删除语言级掌握记录。

### 书签

#### `GET /api/bookmarks`

可选查询参数：`unit_id`。

#### `POST /api/bookmarks`

```json
{
  "unit_id": "ac01-ch01",
  "body_kind": "source",
  "page_index": 2,
  "progress_ratio": 0.4,
  "total_pages": 5,
  "label": "Page 3",
  "excerpt": "In the corner of a first-class smoking carriage...",
  "paragraph_index": 4
}
```

定位时优先使用 excerpt/paragraph，再以页码和比例兜底，降低重新排版造成的偏移。

#### `DELETE /api/bookmarks/{bookmark_id}`

删除指定书签。

### Guided cards

#### `GET /api/agent-cards`

可选查询参数：`current_unit_id`、兼容字段 `current_chapter_id`、`profile_id` 和 `phase`。
它是 WebSocket cards 的 HTTP 兜底入口。

## WebSocket

连接地址：`/ws/reading`。本地开发通常为 `ws://127.0.0.1:8000/ws/reading`。

所有消息都可以携带 `request_id`。Profile 会话通过 `profile_id` 指定；Action 执行时正文自己的
`profile_id` 仍是最终依据。

### 前端发送

#### `hello`

```json
{
  "type": "hello",
  "request_id": "optional-client-id",
  "current_unit_id": "ac01-ch01",
  "profile_id": "english_novel"
}
```

连接建立后发送。`current_chapter_id` 仍作为兼容字段同时发送。

#### `cards`

```json
{
  "type": "cards",
  "request_id": "optional-client-id",
  "current_unit_id": "ac01-ch01",
  "profile_id": "english_novel",
  "phase": "start"
}
```

`phase` 当前常用 `start` 或 `complete`。

#### `action`

```json
{
  "type": "action",
  "request_id": "optional-client-id",
  "action": {
    "id": "generate_annotation",
    "label": "Generate",
    "payload": {
      "unit_id": "ac01-ch01",
      "chapter_id": "ac01-ch01"
    }
  }
}
```

当前没有 `level` 或 Density 字段。每个阅读单元只保存一个译注副本。前端原则上原样发送后端 card
中的 action，不自行拼装业务 payload。

当前 action id：

- `open_chapter`
- `read_original`
- `generate_annotation`
- `open_annotated_copy`
- `mark_chapter_read`
- `start_next_chapter`
- `review_chapter_vocab`

`review_chapter_vocab` 是前端本地视图切换：进入生词表并筛选当前单元，不发送给 Dispatcher。

#### `ping`

后端返回 `pong`，用于连接健康检查。

## 后端事件

### 会话与正文

- `ready`：WebSocket 可用，包含 `protocol=reading.v1`。
- `cards.updated`：替换当前 cards，并更新 `current_unit_id`。
- `chapter.loading`：正文即将打开，包含 `unit_id` 和 `body_kind`。
- `chapter.opened`：正文已打开；优先读取 `unit`，`chapter` 是旧命名兼容副本。
- `unit.marked_read`：阅读单元已标记完成。
- `pong`：心跳响应。
- `error`：传输或 Action 错误，结构为 `{ error: { code, message } }`。

`body_kind` 当前为 `source` 或 `annotated`。

### 译注事件

- `annotation.started`：整章译注开始。
- `annotation.progress`：分块进度，可能包含 `stage/current/total/chunk_index/message`。
- `annotation.model_retry`：Provider 正在重试某个 chunk，包含 `chunk_index` 和 `message`。
- `annotation.degraded`：单个 chunk 已回退原文，包含 `category/code/chunk_index/message`。
- `annotation.completed`：流程完成，随后会发送 `chapter.opened`。
- `annotation.failed`：未分类异常导致整章任务失败。

`annotation.completed` 的重要字段：

```ts
type AnnotationCompletedPayload = {
  unit_id: string
  status: "completed" | "degraded"
  persisted: boolean
  vocabulary_count: number
  stored_vocabulary_count: number
  validated_chunk_count: number
  total_chunk_count: number
  degraded_chunk_count: number
  provider_error_count: number
  validation_error_count: number
}
```

部分 chunk 降级时，后端会合并并保存可用结果；全部 chunk 降级时 `persisted=false`，随后以
`body_kind=source` 打开完整原文。前端不应把 `annotation.degraded` 当作整章失败。

当前 `useReadingSocket` 会显示 retry、progress 和最终状态，并按 `provider`、`validation` 汇总
`annotation.degraded`。降级提示独立于整章错误显示，随后自动打开正文时仍会保留；未知事件会被安全忽略。

常见 WebSocket error code：

- `invalid_message`
- `missing_action`
- `missing_unit_id`
- `unit_not_found`
- `unsupported_action`
- `annotator_not_configured`
- `internal_error`

错误不应清空已经打开的正文。

## 核心数据模型

```ts
type AgentAction = {
  id: string
  label: string
  payload: Record<string, unknown>
}

type AgentCard = {
  id: string
  type: string
  title: string
  body: string
  actions: AgentAction[]
}

type ReadingUnitMeta = {
  id: string
  chapter_id: string
  book_id: string
  book_title: string
  chapter_no: number
  chapter_title: string
  section_no: number
  section_count: number
  summary: string
  has_annotated_copy: boolean
  status: "unread" | "read" | string
  vocab_count: number
  profile_id: string
  language_id: string
}

type ReadingUnitDetail = {
  meta: ReadingUnitMeta
  body: string
  body_kind: "source" | "annotated"
}

type VocabularyEntry = {
  id: number
  book_id: string
  profile_id: string
  language_id: string
  word: string
  translation: string
  global_translation: string
  pos: string
  mastered: boolean
  context: string
  encounter_count: number
  unit_id: string
  chapter_id: string
  first_seen_at: string
  last_seen_at: string
}
```

## 前端对齐原则

1. Guided flow 以服务端 cards 为准；前端只处理明确的本地 action。
2. Profile、collection、book 和 unit 是不同层级，不用 `profile_id` 代替系列标识。
3. Density 分级已取消，不再发送或保存 `level`。
4. 译注副本按 unit 唯一；原文与译注通过 `body_kind` 区分。
5. 书中词条按书隔离，语言级掌握状态共享。
6. 模型重试、chunk 降级和整章失败是不同状态，不根据易变文案判断类型。
7. 前端渲染覆盖层可以即时增加或隐藏单词，但不修改后端保存的原文或译注 Markdown。
8. 断线和错误时保留最后正文、cards 和书签上下文。
9. 可被重复触发的异步读取使用 request revision，只有最新请求可以更新页面状态。

## 已知边界与后续方向

- 查词目前只支持点击单词；尚无框选短语交互。
- `annotation.json_repair` 和 `annotation.not_ready` 仅剩前端兼容分支，可在后续清理。
- 书签后续可增加备注、选中文本锚点和独立管理视图。
- 生词复习可在当前列表之外扩展 flashcard 或 quiz。
- 组件测试与 e2e 应优先覆盖三级目录、Profile 切换、显式书签、译注降级和分页边界。
