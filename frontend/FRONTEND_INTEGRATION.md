# Frontend Integration Notes

这份文档只记录前端展示和前后端对接需要知道的内容。后端内部实现细节，例如 provider、corpus 扫描、memory/storage 写入、dispatcher 执行逻辑，不在这里展开。

## 前端目标

前端的核心不是自由聊天，而是一个受控阅读界面：

- 展示当前阅读内容。
- 展示后端给出的下一步选项 cards。
- 用户通过 card actions 推动流程。
- 实时显示加载、模型生成、重试、失败、完成等状态。
- 为生词复习保留清晰入口。

推荐把页面理解成三块：

1. 阅读区：显示原文或译注正文。
2. 引导区：显示当前 cards 和 actions。
3. 状态区：显示连接状态、加载状态、模型进度、错误信息。

## 第一版阅读界面

当前前端采用固定纸张窗口，而不是左右分栏调试布局。

核心设计：

- 阅读内容显示在固定高度的纸张窗口中。
- 第一版分页使用固定窗口 + CSS columns 的伪分页，让浏览器按真实排版切页。
- 用户通过左右按钮、方向键或空格翻页。
- 正文最后一页之后进入引导页，集中展示后端 cards。
- 译注生成中不清空上下文，而是在纸张中央展示 summary。
- 长文本译注由后端分块并发处理、后端合并保存；前端只展示进度，不展示 chunk 正文预览。
- 进度、重试、JSON 修复、错误信息以小字显示在 summary 上方或纸张顶部。

当前页面模式可以理解为：

```ts
type ReaderMode = "empty" | "reading" | "guidance" | "generating" | "error"
```

后续升级方向：

1. 固定窗口保留不变。
2. 后续建立书签系统，用于章节内精细定位、继续阅读和回看。
3. 再考虑双页书本、翻页动画、阅读位置恢复。
4. 阅读位置恢复暂定保存 `unit_id`、`body_kind`、`page_index`、`progress_ratio` 与可选书签锚点；由于分页受窗口尺寸和字体影响，恢复时优先按书签或比例映射到当前总页数。

## HTTP API

### `GET /api/health`

用途：检查后端是否可用。

典型返回：

```json
{
  "status": "ok"
}
```

前端用途：启动时或调试面板中显示后端连接状态。

### `GET /api/units`

用途：获取所有阅读单元的元数据。

返回类型：`ReadingUnitMeta[]`

前端用途：

- 构建章节/阅读单元列表。
- 显示书名、章节名、切分进度。
- 判断某个单元是否已有译注副本。

### `GET /api/units/{unit_id}`

用途：按 id 获取一个阅读单元正文。

返回类型：`ReadingUnitDetail`

前端用途：

- 非 WebSocket 场景下直接加载原文。
- 调试或兜底读取。

常规阅读流程更推荐通过 WebSocket action 打开正文，因为 WebSocket 会同步返回事件和 cards。

### `GET /api/vocabulary`

用途：获取生词列表。

可选查询：

- `unit_id`
- `chapter_id`

返回类型：`VocabularyEntry[]`

前端用途：

- 展示当前单元生词。
- 展示章节生词。
- 后续扩展复习界面。

### `GET /api/agent-cards`

用途：获取当前应展示的引导 cards。

可选查询：

- `current_unit_id`
- `current_chapter_id`，兼容旧命名

返回类型：`AgentCard[]`

前端用途：

- 首次加载时获取默认推荐动作。
- WebSocket 不可用时的兜底。

常规情况下，WebSocket 会主动推送 `cards.updated`。

## WebSocket

连接地址：

```text
/ws/reading
```

开发环境通常是：

```text
ws://127.0.0.1:8000/ws/reading
```

WebSocket 是主阅读流程的推荐通道，因为它支持后端实时推送加载和模型进度。

## 前端发送消息

### `hello`

用途：初始化会话，告诉后端当前阅读位置。

```json
{
  "type": "hello",
  "request_id": "optional-client-id",
  "current_unit_id": "hp01-ch01"
}
```

`current_unit_id` 可省略。省略时后端会根据 memory 或第一节返回 cards。

### `ping`

用途：心跳或调试。

```json
{
  "type": "ping",
  "request_id": "ping-1"
}
```

后端返回 `pong`。

### `action`

用途：用户点击 card action 后发送给后端。

```json
{
  "type": "action",
  "request_id": "action-1",
  "action": {
    "id": "generate_annotation",
    "label": "生成译注",
    "payload": {
      "unit_id": "hp01-ch01",
      "chapter_id": "hp01-ch01"
    }
  }
}
```

前端不要自行推断复杂流程。优先原样发送后端 card 中给出的 action。

## 后端推送事件

### `ready`

含义：WebSocket 已连接，协议可用。

```json
{
  "type": "ready",
  "protocol": "reading.v1"
}
```

前端建议：连接状态切到 online。

### `cards.updated`

含义：后端给出当前可选动作。

```json
{
  "type": "cards.updated",
  "current_unit_id": "hp01-ch01",
  "cards": []
}
```

前端建议：刷新引导区，不要把旧 actions 混在一起。

### `chapter.loading`

含义：后端开始加载某个阅读单元。

```json
{
  "type": "chapter.loading",
  "unit_id": "hp01-ch01",
  "body_kind": "source"
}
```

`body_kind` 可能是：

- `source`：原文
- `annotated`：译注副本

前端建议：阅读区显示 loading 状态。

### `chapter.opened`

含义：正文已经打开。

```json
{
  "type": "chapter.opened",
  "action_id": "open_chapter",
  "unit": {
    "meta": {},
    "body": "...",
    "body_kind": "source"
  },
  "chapter": {}
}
```

前端建议：优先使用 `unit` 字段。`chapter` 是兼容旧命名。

### `annotation.started`

含义：译注生成流程开始。

前端建议：显示生成状态，禁用重复点击生成按钮。

### `annotation.progress`

含义：译注生成过程中的普通进度。

可能字段：

- `unit_id`
- `stage`
- `current`
- `total`
- `message`

前端建议：状态区显示 `message`。生成译注时保持 summary 页面，不拼接或预览 chunk 正文；最终译注以后端随后推送的 `chapter.opened` 为准。

### `annotation.model_retry`

含义：模型调用出现可重试错误，后端正在等待并重试。

```json
{
  "type": "annotation.model_retry",
  "message": "Model request failed, retrying in 1s."
}
```

前端建议：显示为温和提醒，不要立刻标记失败。

### `annotation.json_repair`

含义：模型返回内容不是有效 JSON，后端正在要求模型修复。

```json
{
  "type": "annotation.json_repair",
  "attempt": 1,
  "message": "模型返回不是有效 JSON，正在请求修复。"
}
```

前端建议：显示为处理中状态。

### `annotation.completed`

含义：译注生成完成，并已保存副本和生词数据。

可能字段：

- `unit_id`
- `vocabulary_count`
- `stored_vocabulary_count`

前端建议：显示完成状态。随后通常还会收到 `chapter.opened` 和 `cards.updated`。

### `annotation.failed`

含义：译注生成失败。

```json
{
  "type": "annotation.failed",
  "unit_id": "hp01-ch01",
  "message": "..."
}
```

前端建议：显示错误，并允许用户重试或阅读原文。

### `unit.marked_read`

含义：当前阅读单元已标记为已读。

前端建议：更新阅读状态。随后通常会收到新的 `cards.updated`。

### `error`

含义：后端无法处理某条消息或 action。

```json
{
  "type": "error",
  "error": {
    "code": "internal_error",
    "message": "后端执行 action 时发生未知错误。"
  }
}
```

常见 code：

- `invalid_message`
- `missing_action`
- `missing_unit_id`
- `unit_not_found`
- `unsupported_action`
- `annotated_copy_not_found`
- `annotator_not_configured`
- `internal_error`

前端建议：根据 code 决定提示方式。`internal_error` 应显示明确失败状态，但不要让整个页面崩掉。

### `pong`

含义：心跳响应。

前端建议：用于连接健康状态，不需要展示给普通用户。

## 数据模型

### `AgentCard`

```ts
type AgentCard = {
  id: string
  type: string
  title: string
  body: string
  actions: AgentAction[]
}
```

前端展示：

- `title` 作为卡片标题。
- `body` 作为卡片说明。
- `actions` 渲染为按钮。

### `AgentAction`

```ts
type AgentAction = {
  id: string
  label: string
  payload: Record<string, unknown>
}
```

前端处理：

- 按钮文字使用 `label`。
- 点击后原样通过 WebSocket `action` 消息发送。
- 不建议前端手写 payload，除非是明确的本地兜底逻辑。

### `ReadingUnitMeta`

```ts
type ReadingUnitMeta = {
  id: string
  chapter_id: string
  book_id: string
  book_title: string
  chapter_no: number
  chapter_title: string
  section_no?: number
  section_count?: number
  summary: string
  has_annotated_copy: boolean
  status: string
}
```

前端展示：

- `book_title`：书名。
- `chapter_no` + `chapter_title`：章节标题。
- `section_no` / `section_count`：旧版阅读单元兼容字段；章节粒度下前端不再展示。
- `summary`：章节或单元概要。
- `has_annotated_copy`：是否已有译注副本。

### `ReadingUnitDetail`

```ts
type ReadingUnitDetail = {
  meta: ReadingUnitMeta
  body: string
  body_kind: "source" | "annotated" | string
}
```

前端展示：

- `body_kind = source` 时展示原文。
- `body_kind = annotated` 时展示译注内容。

### `VocabularyEntry`

```ts
type VocabularyEntry = {
  id: number
  word: string
  translation: string
  global_translation: string
  mastered: boolean
  context: string
  encounter_count: number
  unit_id: string
  chapter_id: string
  first_seen_at: string
  last_seen_at: string
}
```

前端展示：

- 当前单元词汇列表。
- 章节词汇复习。
- 后续可扩展 mastered 状态切换。

## 推荐前端状态

建议前端至少维护这些状态：

```ts
type ReadingConnectionStatus = "connecting" | "online" | "offline" | "error"

type ReadingLoadStatus =
  | "idle"
  | "loading_unit"
  | "generating_annotation"
  | "model_retrying"
  | "json_repairing"
  | "failed"
  | "completed"
```

核心状态建议包括：

- `connectionStatus`
- `loadStatus`
- `currentUnit`
- `currentBody`
- `bodyKind`
- `cards`
- `lastProgressMessage`
- `lastError`
- `vocabulary`

## 推荐事件处理策略

- `ready`：连接成功。
- `cards.updated`：替换 cards。
- `chapter.loading`：进入正文 loading。
- `chapter.opened`：更新正文和当前 unit。
- `annotation.started`：进入译注生成状态。
- `annotation.progress`：更新进度文案。
- `annotation.model_retry`：显示重试中。
- `annotation.json_repair`：显示修复中。
- `annotation.completed`：显示完成，可等待后续 `chapter.opened`。
- `annotation.failed`：显示失败，可允许重试。
- `unit.marked_read`：更新已读状态。
- `error`：根据 code 显示错误，不要清空正文。

## UI 对齐原则

1. 用户只通过后端提供的 actions 推进流程。
2. 当前正文和当前 cards 是页面最重要的信息。
3. 进度事件应该可见，但不要打断阅读。
4. 错误提示要保留用户的上下文，不要把页面重置为空。
5. WebSocket 断开时，页面可以保留最后一次正文和 cards，并提示重连。
6. 生词复习入口可以先作为 card action 展示，具体复习页后续再细化。

## 后续前端任务拆分

1. 建立 WebSocket client 和事件分发器。
2. 建立阅读页面状态 store。
3. 渲染 cards/actions。
4. 渲染 source/annotated 正文。
5. 展示 annotation 进度、重试、失败、完成状态。
6. 接入 vocabulary 列表。
7. 设计断线重连和错误恢复体验。
8. 后续接入阅读位置保存：翻页后节流发送当前位置，重新打开同一章节后恢复到最近页。
9. 设计书签系统：支持章节内书签、继续阅读锚点、从侧边栏定位到书签，以及动态词汇状态变化后的阅读位置恢复。
