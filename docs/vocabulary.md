# Vocabulary Storage

SuperHP Agent 第一版生词存储使用 SQLite，数据库位置：

```text
backend/data/superhp.sqlite3
```

## Tables

- `vocabulary`：全局词条表，按 `word` 去重。
- `unit_vocabulary`：阅读单元与词条的关联表，记录 `unit_id`、`chapter_id`、上下文、出现次数。
- `units`：同步阅读单元 metadata，便于后续做进度和聚合。

## Write Flow

`generate_annotation` 成功后：

1. 保存 `{unit_id}.annotated.md`。
2. 将 `AnnotationResult.vocabulary` 写入 `vocabulary` 和 `unit_vocabulary`。
3. 推送 `annotation.completed`，事件中包含 `stored_vocabulary_count`。
4. Router 重新生成 cards 时会通过 DB 得到 `vocab_count`。

## Query API

```http
GET /api/vocabulary
GET /api/vocabulary?unit_id=hp01-ch01
GET /api/vocabulary?chapter_id=hp01-ch01
```

返回字段包括：`word`、`translation`、`context`、`encounter_count`、`unit_id`、`chapter_id`、`mastered`。

## Next Steps

- 接入点击查词插件，把用户手动查询/收藏的词也写入同一套表。
- 做 `review_chapter_vocab` action 和前端复习界面。
- 增加 mastered 状态更新 API。
