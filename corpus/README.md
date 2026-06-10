# Harry Potter Novel Corpus

英文原版哈利波特小说语料库，按**章→节**两级拆分，便于阅读和检索。

## 目录结构

```
corpus/
├── hp01/
│   ├── ch01/          # Chapter 1: The Boy Who Lived
│   │   ├── 01.md      #   section 1 of 4
│   │   ├── 02.md      #   section 2 of 4
│   │   └── ...
│   ├── ch02/
│   └── ...
├── hp02/
├── hp03/
├── hp04/
└── README.md
```

每节按原文场景断点（`\*` 分隔符）切分，单节约 5–15 分钟阅读量。

## 文件格式

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
summary: "Mysterious letters addressed to..."
---
```

| 字段 | 说明 |
|------|------|
| id | 唯一标识：{book}-ch{章}-sec{节} |
| chapter_id | 章节标识：{book}-ch{章}，用于按章分组 |
| `book_id` | 所属书籍 |
| `book_title` | 书全名 |
| `chapter_no` | 章节序号 |
| `chapter_title` | 章节英文标题 |
| `section_no` | 当前节序号（1-based） |
| `section_count` | 本章总节数 |
| `summary` | 整个章的内容摘要 |

## 书籍列表

| book_id | 书名 | 章数 | 节数 |
|---------|------|------|------|
| hp01 | Harry Potter and the Philosopher's Stone | 17 | 59 |
| hp02 | Harry Potter and the Chamber of Secrets | 18 | 52 |
| hp03 | Harry Potter and the Prisoner of Azkaban | 22 | 60 |
| hp04 | Harry Potter and the Goblet of Fire | 37 | 69 |
| hp05 | Harry Potter and the Order of the Phoenix | - | - |
| hp06 | Harry Potter and the Half-Blood Prince | - | - |
| hp07 | Harry Potter and the Deathly Hallows | - | - |

## 节大小分布

| 分位 | 大小 | 约阅读时间 |
|------|------|------------|
| 中位数 | 9 KB | 5-8 分钟 |
| P75 | 16 KB | 8-12 分钟 |
| P90 | 27 KB | 15-20 分钟 |
| 最长 | 44 KB | 25-30 分钟 |
