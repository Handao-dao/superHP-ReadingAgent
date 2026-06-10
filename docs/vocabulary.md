# Vocabulary Storage

SuperHP Agent 第一版生词存储使用 SQLite，数据库位置：

```text
backend/data/superhp.sqlite3
```

## Tables

- `vocabulary`：全局词条表，按 `word` 去重。
- `unit_vocabulary`：阅读单元与词条的关联表，记录 `unit_id`、`chapter_id`、上下文、出现次数。
- `units`：同步阅读单元 metadata，便于后续做进度和聚合。

`vocabulary` 当前字段包含：

- `word`
- `translation`
- `pos`：`noun / verb / adjective / adverb / phrase / other`
- `mastered`
- `mastered_at`
- `first_seen_at`
- `last_seen_at`

## Write Flow

`generate_annotation` 成功后：

1. 保存 `{unit_id}.{level}.annotated.md`。
2. 将 `AnnotationResult.vocabulary` 写入 `vocabulary` 和 `unit_vocabulary`。
3. 推送 `annotation.completed`，事件中包含 `stored_vocabulary_count`。
4. Router 重新生成 cards 时会通过 DB 得到 `vocab_count`。

注意：批量译注抽取的词性目前默认是 `other`，因为 annotator 还没有输出 `pos`。

用户点击查词并添加生词时：

1. 前端调用 `POST /api/word-lookup` 获取 `word_cn/sentence_cn/pos`。
2. 前端调用 `POST /api/vocabulary` 写入词条和当前 `unit_id` 关联。
3. 后端清理 context 中的 `[[word|translation]]` 标记，保存原文上下文。
4. 前端把该词加入当前阅读页的手动标注覆盖层，并重新分页。

## Query API

```http
GET /api/vocabulary
GET /api/vocabulary?unit_id=hp01-ch01
GET /api/vocabulary?chapter_id=hp01-ch01
```

返回字段包括：`word`、`translation`、`context`、`encounter_count`、`unit_id`、`chapter_id`、`mastered`。

### Mutation API

```http
POST /api/vocabulary
PATCH /api/vocabulary/{vocab_id}/master
DELETE /api/vocabulary/{vocab_id}
POST /api/vocabulary/mark-by-word
POST /api/word-lookup
```

## Frontend Behavior

- 生词表页面支持未掌握/已掌握 tab。
- 支持搜索、全部章节/指定章节筛选。
- 支持删除、标记掌握、重新学习。
- `review_chapter_vocab` card action 会打开生词表并筛选当前章节。
- 阅读页点击任意英文词可以查词。
- 添加生词会即时渲染为手动标注。
- 取消标注会把词标记为 mastered，并在当前阅读页隐藏标注。
- 目录中的词数显示当前章节未掌握词数。

## Remaining Work

- 自动译注词性：让 annotator 也输出 `pos`，或做后台补全。
- 生词复习模式：flashcard、quiz、spaced repetition。
- 同一个词跨章节的来源聚合展示。
- 用户维度：未来如果支持多用户，需要把 mastered/manual 状态从本地单用户数据拆出。
