# Corpus Format

SuperHP Agent 使用章节级 Markdown 文件作为小说语料。目录按“书 -> 章”组织，每个 `.md` 文件是一章完整文本。

## Required Frontmatter

```yaml
---
id: hp01-ch03
chapter_id: hp01-ch03
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 3
chapter_title: "The Letters from No One"
summary: "Mysterious letters addressed to Harry arrive at Privet Drive..."
---
```

## Field Meaning

- `id`：全项目唯一章节 ID，格式推荐 `{book_id}-ch{chapter_no:02d}`。
- `chapter_id`：章节分组 ID，通常与 `id` 相同。
- `book_id` / `book_title`：所属书籍。
- `chapter_no` / `chapter_title`：原小说章节信息。
- `summary`：本章摘要，用于 guided card 和阅读前上下文。

## Rules

- 后端只通过 `id` 读取章节，不接受任意文件路径。
- 原始文本保存在 `corpus/`。
- 译注副本保存到 `backend/data/annotated_corpus/{unit_id}.annotated.md`。
- 生词关联记录到 `unit_id` / `chapter_id`，二者在章节粒度下通常相同。
- 正文内的精细定位后续通过书签系统实现，而不是继续拆分章节文件。
