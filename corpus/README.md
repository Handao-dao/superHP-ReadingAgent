# Harry Potter Novel Corpus

英文原版哈利波特小说语料库，按**书→章**组织，便于阅读和检索。章节内的精细定位后续由书签系统处理。

## 目录结构

```
corpus/
├── hp01/
│   ├── hp01-ch01.md   # Chapter 1: The Boy Who Lived
│   ├── hp01-ch02.md
│   └── ...
├── hp02/
├── hp03/
├── hp04/
└── README.md
```

每个 Markdown 文件是一章完整原文。

## 文件格式

```yaml
---
id: hp01-ch03
chapter_id: hp01-ch03
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 3
chapter_title: "The Letters from No One"
summary: "Mysterious letters addressed to..."
---
```

| 字段 | 说明 |
|------|------|
| id | 唯一标识：{book}-ch{章} |
| chapter_id | 章节标识：{book}-ch{章}，通常与 id 相同 |
| `book_id` | 所属书籍 |
| `book_title` | 书全名 |
| `chapter_no` | 章节序号 |
| `chapter_title` | 章节英文标题 |
| `summary` | 整个章的内容摘要 |

## 书籍列表

| book_id | 书名 | 章数 |
|---------|------|------|
| hp01 | Harry Potter and the Philosopher's Stone | 17 |
| hp02 | Harry Potter and the Chamber of Secrets | 18 |
| hp03 | Harry Potter and the Prisoner of Azkaban | 22 |
| hp04 | Harry Potter and the Goblet of Fire | 37 |
| hp05 | Harry Potter and the Order of the Phoenix | - |
| hp06 | Harry Potter and the Half-Blood Prince | - |
| hp07 | Harry Potter and the Deathly Hallows | - |
