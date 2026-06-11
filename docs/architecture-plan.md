# SuperHP Agent 架构与实操状态

## Summary

SuperHP Agent 已从“粘贴文本的通用标注工具”升级为“阅读单元驱动的《哈利波特》专门阅读助手”。当前主流程已经闭环：用户从目录选择章节，通过 guided cards 生成/打开译注或阅读原文，在固定纸面中伪分页阅读，并可查词、添加生词、复习本章生词、标记已读和进入下一章。

后端采用明确分层：transport 负责 HTTP/WebSocket，runtime 负责 cards 与 action side effects，services 负责模型译注和查词，storage/memory/corpus 负责本地数据。Router 只决定“给用户什么选项”，Dispatcher 才执行“用户选择之后发生什么”。

## Completed Backend

- `CorpusStore` 已支持扫描 `corpus/` Markdown、解析 YAML frontmatter、按 `unit_id` 安全读取正文，并拒绝路径越界与重复 id。
- Provider 抽象、OpenAI-compatible provider、模型重试与错误归一化已完成。
- `AnnotatorService` 已支持段落完整分块、并发标注、模型重试、JSON 修复、截断检测、合并译注，并从 `[[word|translation]]` 中提取生词。
- `WordLookupService` 已支持上下文查词，返回 `word_cn/sentence_cn/pos`。
- WebSocket reading session 已支持 `ready/cards.updated/chapter.loading/chapter.opened/annotation.* /unit.marked_read/error`。
- Guided cards 已支持 start/complete 两个阶段：生成译注、打开译注、阅读原文、读下一章、复习生词、回看正文。
- 标注副本已按 Density level 保存为 `{unit_id}.{level}.annotated.md`，legacy `{unit_id}.annotated.md` 作为 intermediate fallback。
- SQLite 已接入 `units/vocabulary/unit_vocabulary`，支持生词上下文、掌握状态、词性、章节关联和未掌握词计数。
- SQLite 已接入 `bookmarks`，支持显式当前页书签、原文/译注模式、页码和比例定位。
- Memory 已记录 current/opened/read/annotated unit ids 和 event log；WebSocket 初始 cards 会解析并回传真实 current unit id。
- HTTP 已提供 units、unit detail、bookmarks、vocabulary CRUD/mark、word lookup、agent cards 等接口。

## Completed Frontend

- 主界面已是三栏阅读壳：左侧目录、中央固定纸面阅读器、移动端目录抽屉。
- 目录按书分组，显示当前章、已读、已有译注、未掌握生词数，并通过 WebSocket 请求该章 start cards。
- 阅读区采用固定纸面 + CSS columns 伪分页，支持按钮、方向键和空格翻页；正文重排不会误跳 complete card。
- 生成译注时展示 chapter summary 和进度状态；start/complete guidance 页已降级为 action panel，避免重复标题和说明。
- 右上角 Density 下拉使用 `H/M/L`，持久化到 `localStorage` 并注入 generate/open annotated actions。
- 当前章节 id 持久化到 `localStorage`，刷新后可恢复卡片页的章节上下文和 summary。
- 阅读页支持保存显式书签；侧边栏在章节下展示书签，并可直接打开对应原文/译注位置。
- 渲染层支持普通英文词和已标注词点击查词；手动添加标注会写入生词库并即时重排当前正文。
- 生词表页面已支持全部/章节筛选、未掌握/已掌握、搜索、删除、重新学习、词性 badge。
- `review_chapter_vocab` card action 已前端拦截，直接打开生词表并筛选当前章。
- 阅读区域和 card 文案已基本英文化；侧边栏、顶部状态栏、查词与生词表仍保留部分中文。

## Current APIs

- `GET /api/health`
- `GET /api/units`
- `GET /api/units/{unit_id}`
- `GET /api/chapters` / `GET /api/chapters/{chapter_id}`：兼容旧命名，当前仍以 unit 为核心。
- `GET /api/bookmarks?unit_id=...`
- `POST /api/bookmarks`
- `DELETE /api/bookmarks/{bookmark_id}`
- `GET /api/vocabulary?unit_id=...&chapter_id=...`
- `POST /api/vocabulary`
- `PATCH /api/vocabulary/{vocab_id}/master`
- `DELETE /api/vocabulary/{vocab_id}`
- `POST /api/vocabulary/mark-by-word`
- `POST /api/word-lookup`
- `GET /api/agent-cards`
- `WS /ws/reading`

## Remaining Extensions

- 书签增强：选中文本锚点、书签备注、独立书签管理页或跨设备同步。
- 自动译注词性：让 annotator 输出或二次补全 `pos`，避免批量译注生词默认 `other`。
- 生词复习模式：在生词表之外增加 quiz/flashcard/spaced repetition。
- 前端英文化收尾：逐步英文化查词、生词表、状态栏或保留双语策略。
- 更细的用户状态：后续可把 mastered/manual annotations/bookmarks 从本地单用户状态升级到用户维度。

## Test Status

- 后端已有测试覆盖 corpus、memory、provider、router、WebSocket、action dispatcher、annotator/lookup services、storage、main API。
- 当前常规验证命令：

```bash
cd backend
uv run python -m pytest
uv run ruff check .

cd ../frontend
npm run build
```

## Assumptions

- 小说文本作为本地个人学习资料放入 `corpus/`，公开仓库应谨慎处理版权文本。
- 首版不做开放问答，不做 RAG，不让 LLM 直接拥有执行权限。
- 工具能力只通过受控 action 或后端 API 间接使用。
- 当前实现默认单用户本地状态，暂不区分账号。
