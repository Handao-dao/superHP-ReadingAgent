# Reading Memory

SuperHP Agent 的 memory 第一版采用本地文件存储，不引入数据库依赖。它只记录产品需要的阅读状态和调试/审计需要的事件日志，不保存自由对话历史。

## Files

```text
backend/data/memory/
├── reading_memory.json
└── events.jsonl
```

## reading_memory.json

`reading_memory.json` 保存当前用户的阅读进度。文件不存在或内容为空时，系统认为用户还没有开始阅读，Router 会默认展示从第一个阅读单元开始的 guided card。

```json
{
  "current_unit_id": "hp01-ch01",
  "opened_unit_ids": ["hp01-ch01"],
  "read_unit_ids": [],
  "annotated_unit_ids": [],
  "updated_at": "2026-06-09T...Z"
}
```

## events.jsonl

`events.jsonl` 每行一条 JSON，用于记录阅读行为和系统事件。

常见事件：

- `session_started`
- `session_hello`
- `cards_shown`
- `unit_opened`
- `unit_marked_read`
- `annotation_requested`
- `error`

## Design Notes

- `current_unit_id` 是 Router 选择“继续阅读哪里”的主要依据。
- `read_unit_ids` 会让对应章节进入已读状态，从而展示“下一章/复习/回看”类卡片。
- `annotated_unit_ids` 与 `backend/data/annotated_corpus/{unit_id}.annotated.md` 都可表示已标注；后续标注链路完成后应同时写入。
- memory 不替代 vocabulary 数据库；生词仍应由独立表或插件 API 管理。
## Runtime Boundary

- `ReadingFlowRouter` 只读取状态并生成 guided cards。
- `ActionDispatcher` 根据 `action.id` 找到对应 handler。
- `ActionHandler` 执行副作用，例如打开阅读单元、标记已读、请求译注。
- `ReadingSocketSession` 只负责 WebSocket 协议收发、错误转换和 action 后刷新 cards。
## Future: Reading Position

后续可在 `reading_memory.json` 中增加阅读位置记录，用于恢复用户退出前的翻页位置。第一版建议存成按 `unit_id` 索引的轻量对象：

```json
{
  "positions": {
    "hp01-ch01": {
      "body_kind": "annotated",
      "page_index": 4,
      "progress_ratio": 0.36,
      "updated_at": "2026-06-10T...Z"
    }
  }
}
```

`page_index` 适合直接恢复同一窗口下的位置；`progress_ratio` 更适合在窗口尺寸、字体或分页算法变化后按比例恢复。
