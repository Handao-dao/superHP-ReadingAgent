# SuperHP Agent

SuperHP Agent 是一个《哈利波特》专门阅读助手工程。它不再以自由粘贴文本为主入口，而是围绕本地 `corpus/` 章节语料、章节译注副本、生词本和选择驱动的 agent 会话卡片来组织阅读流程。

## 产品方向

- 一次选择一章来读。
- 章节文件使用 Markdown + YAML frontmatter。
- 用户不自由发问，只通过阅读卡片选择下一步。
- 标注完成后保存章节译注副本，替代旧项目的历史记录。
- 生词与章节建立关联，支持本章复习和全局掌握状态。
- 工具能力只在受控 action 内部使用，不能越过 `corpus/` 读取范围。

## 当前能力

- 按“书 -> 章”扫描 `corpus/`，当前章节粒度由 Markdown frontmatter 定义。
- 左侧目录显示章节列表、已读状态、已有译注状态和未掌握生词数。
- 阅读流程由 guided cards 推进，不提供自由聊天输入。
- 支持 `H / M / L` 三档 Density，分别映射到高/中/低标注密度。
- 生成译注后保存为 level-specific annotated copy，例如 `hp01-ch01.intermediate.annotated.md`。
- 已生成译注可回看；旧版 `{unit_id}.annotated.md` 作为 intermediate 兼容 fallback。
- 阅读区使用固定纸面 + CSS columns 伪分页，支持左右按钮、方向键和空格翻页。
- 阅读到最后一页后进入 complete card，可读下一章、复习生词或回看正文。
- 支持显式书签：阅读页保存当前页，从侧边栏章节下方回到对应原文/译注位置。
- 阅读译注时支持点击任意英文词查词、添加标注、取消标注/标记已掌握。
- 生词表支持未掌握/已掌握、搜索、章节筛选、删除、重新学习和词性展示。
- 前端会持久化当前章节与 Density，刷新后可恢复当前 card 上下文。

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
summary: "Chapter summary."
---

Chapter body...
```

> 注意：小说原文和 EPUB 仅建议作为本地个人学习资料使用。公开仓库中应谨慎处理受版权保护文本。

## 待扩展方向

1. 书签增强：后续可支持选中文本书签、书签备注和独立书签管理页。
2. 自动译注生词的词性增强：当前手动查词能保存 `pos`，批量译注抽词仍默认 `other`。
3. 生词复习训练：在生词表之外增加 quiz/flashcard 等复习模式。
4. 前端英文化收尾：当前侧边栏、顶部状态栏、查词和生词表仍保留部分中文。
