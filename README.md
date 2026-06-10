# SuperHP Agent

SuperHP Agent 是一个《哈利波特》专门阅读助手工程。它不再以自由粘贴文本为主入口，而是围绕本地 `corpus/` 章节语料、章节译注副本、生词本和选择驱动的 agent 会话卡片来组织阅读流程。

## 产品方向

- 一次选择一章来读。
- 章节文件使用 Markdown + YAML frontmatter。
- 用户不自由发问，只通过阅读卡片选择下一步。
- 标注完成后保存章节译注副本，替代旧项目的历史记录。
- 生词与章节建立关联，支持本章复习和全局掌握状态。
- 工具能力只在受控 action 内部使用，不能越过 `corpus/` 读取范围。

## 当前目录

```text
superhp_Agent/
├── backend/              # FastAPI backend skeleton
├── frontend/             # Vue guided reading UI skeleton
├── corpus/               # Local chapter markdown files
├── docs/                 # Architecture and implementation notes
└── extract_chapters.py   # Existing EPUB extraction helper
```

## Corpus 文件格式

```md
---
id: hp01-ch01
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 1
chapter_title: "The Boy Who Lived"
summary_zh: 本章中文摘要，可后续补充。
---

Chapter body...
```

> 注意：小说原文和 EPUB 仅建议作为本地个人学习资料使用。公开仓库中应谨慎处理受版权保护文本。

## 下一步

1. 完成 `CorpusStore` 与章节 API。
2. 接入 SQLite chapter / vocabulary / progress schema。
3. 把旧项目的标注、查词和 SSE 能力迁移到章节任务。
4. 将前端改造成 guided cards + chapter reader。
