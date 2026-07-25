# English Novel Corpus

英文原版小说语料库，按**书→章**组织，便于阅读和检索。章节内的精细定位后续由书签系统处理。

## 目录结构

```
corpus/
├── catalog.yaml            # 系列、图书顺序和可选 selection policy
├── book_difficulty_catalog.example.yaml  # 选书难度目录模板
├── book_difficulty_catalog.yaml  # 本地真实数据，默认不进入 Git
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

## 图书难度目录

`book_difficulty_catalog.yaml` 是未来选书 Agent 使用的小型本地目录，与
`catalog.yaml` 的职责不同：

- `catalog.yaml` 管理当前本地图书馆的系列、顺序和 selection policy。
- `book_difficulty_catalog.yaml` 管理推荐所需的 ISBN、蓝思值、题材和可用性。

先从版本库中的模板创建本地文件：

```powershell
Copy-Item corpus/book_difficulty_catalog.example.yaml `
  corpus/book_difficulty_catalog.yaml
```

本地文件初始为空，不影响当前阅读主链路，并已加入 `.gitignore`，避免把受来源许可约束的真实
蓝思数据意外提交到公开仓库。添加图书时建议使用以下格式：

```yaml
version: 1
books:
  - id: stable-catalog-id
    local_book_id: hp01
    title: Example Book
    author: Example Author
    isbn: "9780000000000"
    fiction: true
    genres:
      - fantasy
      - adventure
    series:
      title: Example Series
      index: 1
    page_count: 240
    summary: Short, spoiler-safe summary.
    source_url: https://example.com/verified-record
    lexile:
      measure: 760
      code: null
      certified: true
      source: user_supplied
      verified_at: 2026-07-25
```

维护规则：

- ISBN 会去除空格和连字符后保存，支持 ISBN-10 与 ISBN-13。
- 同一个目录不能出现重复 `id` 或重复 ISBN。
- `local_book_id` 存在时表示该书已在 `corpus/` 中可读；未填写时只是外部候选。
- `genres` 使用小写英文标签，搜索多个标签时匹配其中任意一个。
- `certified: true` 只用于来自正式来源且与 ISBN 版本一致的蓝思值。
- 暂时没有 ISBN 时可以保存非认证数据，但必须将 `certified` 设为 `false`。
- 不通过程序自动访问或抓取 Lexile Find a Book；正式自动查询需要授权 API。

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
