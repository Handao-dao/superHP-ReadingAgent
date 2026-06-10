# Corpus Format

SuperHP Agent 使用阅读单元级 Markdown 文件作为小说语料。目录按“书 -> 章 -> 节”组织，每个 `.md` 文件是一段适合一次阅读的 section。

## Required Frontmatter

```yaml
---
id: hp01-ch03-sec01
chapter_id: hp01-ch03
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 3
chapter_title: "The Letters from No One"
section_no: 1
section_count: 7
summary: "Mysterious letters addressed to Harry arrive at Privet Drive..."
---
```

## Field Meaning

- `id`：全项目唯一阅读单元 ID，格式推荐 `{book_id}-ch{chapter_no:02d}-sec{section_no:02d}`。
- `chapter_id`：原小说章节 ID，用于把多个阅读单元归入同一章。
- `book_id` / `book_title`：所属书籍。
- `chapter_no` / `chapter_title`：原小说章节信息。
- `section_no` / `section_count`：当前阅读单元在本章中的位置。
- `summary`：本章摘要，用于 guided card 和阅读前上下文。

## Rules

- 后端只通过 `id` 读取阅读单元，不接受任意文件路径。
- 原始文本保存在 `corpus/`。
- 译注副本保存到 `backend/data/annotated_corpus/{unit_id}.annotated.md`。
- 生词关联优先记录到 `unit_id`，必要时可通过 `chapter_id` 聚合整章复习。
- 首版不在正文中加入段落 ID；阅读粒度由文件切分决定。