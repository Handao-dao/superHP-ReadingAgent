# SuperHP Agent 架构与实操计划

## Summary

把项目从“用户粘贴文本的通用标注工具”升级为“阅读单元驱动的《哈利波特》专门阅读助手”。实施分两条主线推进：

1. **工程化升级**：参考 nanobot 的分层思想，拆出 runtime、provider、storage、event、tool/action、transport 等边界，让后端不再把任务、LLM 初始化、流式返回、保存逻辑集中在入口文件。
2. **特化阅读体验**：引入 `corpus/` Markdown 小说文本，按“书 -> 章 -> 阅读单元(section)”存储；每个阅读单元有唯一 `id`，并通过 `chapter_id` 归属到原小说章节。界面采用选择驱动的 agent cards，不开放自由问答。

首轮目标采用“阅读单元闭环”：能列出阅读单元、打开阅读单元、生成译注、保存译注副本、按阅读单元记录生词、回看已译注文本，并由 guided cards 提供下一步选择。

## Key Changes

- 使用 `Markdown + YAML frontmatter` 存储小说文本。
- `id` 表示阅读单元唯一 ID，例如 `hp01-ch03-sec01`。
- `chapter_id` 表示原小说章节分组 ID，例如 `hp01-ch03`。
- 标注副本保存到 `backend/data/annotated_corpus/{unit_id}.annotated.md`。
- 删除旧的 history 产品形态，回看改为读取阅读单元译注副本。
- 保留全局 vocabulary，同时新增阅读单元与生词关联，后续可按 `chapter_id` 聚合。
- 用户界面不提供自由问答框，只提供 agent cards 和预定义 action。
- 搜索/读取工具严格限制在 `corpus/`，且只通过业务接口调用。
- 传输层采用 WebSocket 承载 guided reading session，HTTP 保留给稳定资源读取和插件接口。

## Backend Plan

1. 拆分工程边界：`config`, `corpus`, `storage`, `runtime`, `tools`, `transport`, `main`。 **已完成基础版**
2. 实现 `CorpusStore`：扫描阅读单元、解析 frontmatter、按 `unit_id` 读取正文、拒绝路径穿越。 **已完成基础版**
3. 实现 Provider 抽象：统一模型调用、重试、流式接口、OpenAI-compatible provider。 **已完成基础版**
4. 实现 deterministic Router 与 guided cards：继续阅读、生成译注、复习本节生词、标记已读、下一节。 **已完成模板版**
5. 实现 WebSocket reading session：连接后推送 cards，action 后推送加载/打开/卡片更新事件。 **已完成基础版**
6. 实现 ActionDispatcher/ActionHandler：Router 只生成选项，Dispatcher 负责 action 分发，Handler 负责副作用执行，Transport 只收发消息。 **已完成基础版**
7. 实现本地 memory：reading_memory.json 记录当前阅读进度，events.jsonl 记录行为日志。 **已完成基础版**
8. 实现 SQLite schema：units/chapters、reading_progress、vocabulary、unit_vocabulary。 **schema 草稿已建，尚未接入业务**
9. 迁移旧项目标注链路：阅读单元文本 -> LLM 标注 -> progress event -> 保存 annotated copy。 **已完成基础版，chunk/批处理待完善**
10. 迁移点击查词：请求中携带 `unit_id`，手动添加生词时关联当前阅读单元。 **部分完成，译注抽词已写入 unit_vocabulary，点击查词待接入**
11. 实现 guided action 的真实副作用：打开原文、生成译注、回看译注、标记已读、读下一节、复习本节生词。 **部分完成，复习生词待接入**

## Frontend Plan

1. 阅读首页改为 guided card + reader。 **已完成基础版**
2. 删除自由文本输入框。 **已完成**
3. 阅读区展示 book、chapter、section、summary、status。 **部分完成**
4. 如果已有译注副本，默认展示译注；否则展示原文和“生成译注”卡片。 **后端状态已支持，译注读取未接入**
5. 生词页支持按阅读单元/章节筛选。 **未完成**
6. 历史页删除或重定向到阅读单元列表/阅读页。 **新项目暂无历史页**

## API Draft

- `GET /api/health` **已完成**
- `GET /api/units` **已完成**
- `GET /api/units/{unit_id}` **已完成**
- `GET /api/chapters` **兼容保留：当前返回阅读单元列表**
- `GET /api/chapters/{chapter_id}` **兼容保留：当前参数实际接收 unit_id**
- `WS /ws/reading` **已完成基础版**
- `POST /api/units/{unit_id}/annotate-task` **未完成**
- `GET /api/units/{unit_id}/annotate-stream?task_id=...` **未完成，可能改为 WS progress event**
- `POST /api/units/{unit_id}/read` **未完成**
- `GET /api/vocabulary?unit_id=...&chapter_id=...` **已完成基础版**
- `GET /api/agent-cards` **已完成兼容版**

## Test Plan

- `CorpusStore` 只能读取 `corpus/` 内阅读单元。 **已覆盖基础路径**
- Markdown frontmatter 解析正确，缺少或重复 `id` 要报错。 **重复 id 已覆盖，缺少字段待补**
- 阅读单元扫描能按 book/chapter/section 排序。 **已覆盖**
- WebSocket 连接能推送 ready/cards，打开单元能返回正文和 metadata。 **已覆盖**
- ActionDispatcher 能分发打开阅读单元、标记已读、未知 action。 **已覆盖**
- Memory 文件为空时 Router 默认从第一个阅读单元开始；存在当前进度时默认继续该单元。 **已覆盖**
- 打开阅读单元、标记已读会写入 memory 并追加事件日志。 **已覆盖**
- 标注 completed 后生成 annotated copy。 **已覆盖基础版**
- 译注副本能通过 `open_annotated_copy` 回看。 **已覆盖基础版**`n- 生词能按 `unit_id` / `chapter_id` 查询。 **已覆盖 storage 层，API 已完成基础版**
- 前端没有自由文本输入框，guided card 按钮能触发对应 action。 **需补 e2e/组件测试**

## Assumptions

- 小说文本由本地加入项目，格式采用 `.md + YAML frontmatter`。
- 首版不做 RAG，不做开放问答，不做用户自由 prompt。
- 工具系统用于受控 action，不直接暴露给用户。
- nanobot 的 subagent、cron、MCP、多渠道能力暂不引入。
