# English Novel Corpus

英文原版小说语料库，按**书→章**组织，便于阅读和检索。章节内的精细定位后续由书签系统处理。

## 目录结构

```
corpus/
├── catalog.yaml            # 系列、图书顺序和可选 selection policy
├── hp01/
│   ├── hp01-ch01.md   # Chapter 1: The Boy Who Lived
│   ├── hp01-ch02.md
│   └── ...
├── hp02/
├── hp03/
├── hp04/
├── ac01/                  # And Then There Were None
├── ac02/                  # Murder on the Orient Express
├── ...
├── ac08/                  # Endless Night
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
| ac01 | And Then There Were None | 18 |
| ac02 | Murder on the Orient Express | 32 |
| ac03 | The Murder of Roger Ackroyd | 27 |
| ac04 | Death on the Nile | 31 |
| ac05 | A Murder Is Announced | 24 |
| ac06 | Five Little Pigs | 20 |
| ac07 | Crooked House | 26 |
| ac08 | Endless Night | 24 |

`ac01` 的最后两个阅读单元分别是原书的 Epilogue 和最终手稿；`ac05` 的最后一个阅读单元是 Epilogue。`ac06` 保留原书的 Book One、Book Two、Book Three 结构，并使用连续的阅读单元编号。
