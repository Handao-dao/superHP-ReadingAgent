# Backend Overview

这份文档用于快速理解后端各部分职责。源码中的注释解释局部实现，这里解释整体分层和模块边界。

后端源码的目标依赖方向、Bus 规划、Contracts / Storage 边界和渐进重构路线见 [`src/superhp_agent/README.md`](src/superhp_agent/README.md)。

## 近期更新记录

### 2026-06-14

- 引入 profile 化文本标注工作流，内置 `english_novel` 与 `classical_chinese`。
- 新增 `ProfileRegistry`，profile 负责 prompt、标注解析、lookup prompt、card copy 和 renderer hint。
- `AnnotatorService` / `LazyAnnotatorService` 支持按阅读单元 `profile_id` 选择 prompt 和 parser。
- WebSocket `hello/cards` 与 HTTP cards API 支持 `profile_id`，可按场景返回对应目录首篇和卡片文案。
- 新增 `GET /api/profiles`，前端可读取当前可用阅读场景。
- `GET /api/units` 支持 `profile_id` 过滤，用于英文小说与文言文目录切换。
- `GET /api/vocabulary` 支持 `profile_id` 过滤；`units` 表补充 `profile_id` 字段并带轻量迁移。
- `POST /api/word-lookup` 与 `mark-by-word` 支持 profile 参数，文言文查词走文言文 lookup prompt。
- `classical_chinese` profile 使用 `[[原文|现代汉语释义|pos]]` 标记，pos 使用中文学习标签，如 `通假字`、`古今异义`、`词类活用`、`虚词用法`、`特殊句式`。
- 添加文言文语料：`论语/学而`、`谏太宗十思疏`、`师说`。

## 总体分层

后端可以理解为五层：

1. 传输层：接收 HTTP/WebSocket 请求，返回前端需要的数据和事件。
2. 运行时层：决定阅读流程中的选项，并执行用户选择的动作。
3. Context 层：用可复用 block 组织模型上下文。
4. 服务层：封装模型调用、译注生成、查词等业务能力。
5. 数据层：读取 corpus，记录 memory，存储 vocabulary 和生成的译注副本。

核心原则是：Router 只决定“给用户什么选项”，Dispatcher 才执行“用户选择之后发生什么”。这样第一版可以保持确定性，也方便以后再引入 LLM 辅助决策。

## 入口与配置

### `src/superhp_agent/main.py`

FastAPI 应用入口，也是后端的组合根。它负责创建并连接这些长期对象：

- `Settings`
- `CorpusStore`
- `ReadingMemoryStore`
- `AppDB`
- `LazyAnnotatorService`
- `ReadingStateReader`
- `ReadingFlowRouter`

HTTP 接口主要提供列表、详情、词汇和卡片读取；WebSocket 接口把实时阅读会话交给 `ReadingSocketSession`。

### `src/superhp_agent/config.py`

集中管理配置和派生路径。重要路径包括：

- `corpus_dir`：原始 Markdown 小说文本目录。
- `data_dir`：运行期数据目录。
- `annotated_dir`：生成后的译注副本目录。
- `reading_memory_path`：用户阅读进度 JSON 文件。
- `event_log_path`：用户行为 JSONL 日志。
- `db_path`：SQLite 数据库路径。
- `llm_max_tokens`：单次模型输出 token 上限，默认 `8192`。
- `annotation_max_chunk_words`：兼容保留的单次译注输入上限名称，默认 `1500`；英文单词、中文单字和标点各按一个粗略单位计量。分块器先按空行划分段落，再在不超过上限的前提下合并完整段落；异常的超长单段会直接报错。
- `annotation_max_concurrency`：标注 chunk 并发数，默认 `8`，可通过环境变量在 `1` 到 `32` 之间调整。

配置优先级遵循 `BaseSettings` 规则：真实环境变量高于 `.env`，`.env` 高于 `Settings` 类中的默认值。

## 文本与数据层

### `src/superhp_agent/corpus.py`

`CorpusStore` 是读取小说文本的唯一入口。外部只能通过 `unit_id` 请求文本，不能传入任意文件路径。

它负责：

- 扫描 `corpus/` 下的 Markdown 文件。
- 解析 YAML frontmatter。
- 生成稳定的阅读单元索引。
- 校验重复 id 和路径越界。
- 返回 `ReadingUnitDocument`。

这里的 `ReadingUnit` 是阅读体验中的最小单元，不一定等同于完整章节。`chapter_id` 用来把同一章切分后的多个 unit 重新关联起来。

### `src/superhp_agent/memory.py`

`ReadingMemoryStore` 负责轻量用户状态，使用 JSON 和 JSONL 文件保存。

它记录：

- 当前阅读单元。
- 打开过的单元。
- 已读单元。
- 已生成译注的单元。
- 行为事件日志。

这个模块适合存“当前流程需要立刻知道”的状态，不适合复杂查询。

### `src/superhp_agent/storage.py`

`AppDB` 是 SQLite 网关，负责更适合查询和聚合的数据。

当前主要保存：

- 阅读单元元数据索引。
- 生词表。
- 单元与生词的关联。
- 生词出现次数、上下文、词性、掌握状态、时间戳。
- 显式书签，包括阅读单元、原文/译注模式、页码、比例、摘要和创建时间。

简单说：memory 管流程状态，storage 管可查询数据。

## 阅读运行时

### `src/superhp_agent/runtime/reading_state.py`

`ReadingStateReader` 把多个数据源合成前端可用的状态：

- corpus 中有哪些阅读单元。
- 哪个单元已有译注副本。
- 哪个单元已读。
- 每个单元关联多少生词。
- 下一个阅读单元是谁。

它是只读聚合器，不应该在这里写入进度或生成文件。

### `src/superhp_agent/runtime/cards.py`

`ReadingCardBuilder` 负责生成用户看到的选项卡片。

例如：

- 第一次开始阅读。
- 当前单元还没有译注，提示生成译注或阅读原文。
- 当前单元已有译注，提示继续阅读、复习单词、标记已读。
- 当前单元已读，提示进入下一节或复习。

卡片文案和 action id 集中在这里，便于以后调整交互体验。

### `src/superhp_agent/runtime/action_router.py`

`ReadingFlowRouter` 是确定性 Router。它根据当前阅读状态选择展示哪些 cards。

第一版不使用 LLM 决策，原因是：

- 阅读助手的流程边界比较清楚。
- 用户不自由提问，而是在有限选项中选择。
- 确定性逻辑更容易测试和调试。

以后如果要引入 LLM，也建议让 LLM 只参与“推荐优先级”或“解释为什么推荐”，不要直接拥有执行权限。

### `src/superhp_agent/runtime/action_dispatcher.py`

`ActionDispatcher` 负责执行用户选择的 action。

典型动作包括：

- 打开原文。
- 打开译注副本。
- 标记已读。
- 调用译注服务生成 annotated Markdown。
- 写入 memory、event log、vocabulary DB。
- 打开译注时会按 action payload 中的 `level` 查找 `{unit_id}.{level}.annotated.md`；如果当前 level 不存在，则自动生成该密度版本。
- legacy `{unit_id}.annotated.md` 作为 intermediate fallback 读取，不做强制迁移。

这里是后端副作用最集中的地方，因此需要保持 handler 小而清楚。

## 后端事件 Hook

### `src/superhp_agent/runtime/events.py`

`EventSink` 是后端行为回传的轻量 hook。业务层可以通过它报告进度和中间状态，但不需要知道这些事件最终会发给 WebSocket、测试收集器，还是未来的 HTTP stream。

当前包含：

- `BackendEvent`：统一事件对象。
- `EventSink`：事件接收协议。
- `CallableEventSink`：兼容旧的 `emit(event_type, **payload)` 函数。
- `NullEventSink`：无输出场景的空实现。

模型译注流程已经接入这个 hook，用于回传模型重试和 JSON 修复状态。WebSocket 传输层通过 `ReadingSocketEventSink` 把这些事件转成前端协议消息。

## 传输层

### `src/superhp_agent/transport/reading_ws.py`

`ReadingSocketSession` 处理一个 WebSocket 阅读会话。

它负责：

- 接受连接。
- 校验客户端消息格式。
- 发送 `ready`、`cards.updated`、`chapter.opened`、`annotation.progress` 等事件。
- 把 action 交给 `ActionDispatcher`。
- 通过 `ReadingSocketEventSink` 转发后端事件。
- 把异常转换成前端可理解的 error 事件。
- 初始和 action 后的 `cards.updated` 会回传 Router 实际解析出的 `current_unit_id`，帮助前端刷新后恢复章节上下文。

它不负责决定业务流程，也不直接生成译注。

## 模型与服务层

### `src/superhp_agent/providers/`

Provider 层抽象模型调用。业务服务依赖 `LLMProvider`，而不是某个厂商 SDK。

主要文件：

- `base.py`：定义 `LLMProvider`、`LLMResponse`、重试逻辑和错误归一化。
- `openai_compat.py`：适配 OpenAI-compatible Chat Completions API。
- `registry.py`：保存 provider 元信息。
- `factory.py`：根据配置创建 provider。

这个设计参考了工程级 agent 项目常见做法：把模型供应商隔离在边界层，避免业务逻辑到处出现 SDK 细节。

## Context 组织层

### `src/superhp_agent/context.py`

`ContextBlock` / `ContextBundle` 是可迁移的模型上下文组件抽象。

当前用途是让标注服务从字符串模板拼接升级为“静态 block 定义 + 运行时 block 实例 + 统一 renderer”：

- 静态 block：长期稳定的规则，例如 `system_policy`、`annotation_contract`、`annotation_examples`、`output_contract`。
- 运行时 block：每次任务开始时由当前状态生成，例如 `density_profile`、`mastered_words`、`reader_text`。
- `ContextBundle.to_messages()` 会把 system blocks 合并成一个 system message，把 user blocks 合并成一个 user message。
- 标注任务会先构建 run-static context，包含 `density_profile`、`mastered_words` 和相关 policy；并发处理 chunk 时只追加最后的 `reader_text` block，以提高稳定前缀的缓存命中。
- Context block 不做持久化；它们是模型调用前的临时上下文组装结果。

后续 lookup、复习、生词训练等模型能力可以复用这层抽象。

## 服务层

### `src/superhp_agent/services/annotator.py`

`AnnotatorService` 负责译注生成。它把“单块模型标注能力”和“长文本分块并发流程”放在同一服务边界内，对外仍然只暴露 `annotate_text()`。

当前流程：

- `AnnotationChunker` 先按自然段识别段落。
- 英文单词、单个中文汉字和标点都粗略计为一个分块单位，默认单次上限为 `1500`。
- 优先按原文段落组装 chunk；加入下一段会超过上限时，先封闭当前 chunk。
- 段落是不可拆分的原子边界；异常的超长单段会明确报错，不进入 Service 调用。
- 多个 chunk 通过 `annotation_max_concurrency` 控制并发，默认 `8`，兼顾长章节生成速度与常规模型 API 的限流风险。
- 每个 chunk 独立调用 provider，返回纯 annotated text。
- 如果 provider 返回 `finish_reason = length`，抛出 `AnnotationTruncatedError`，不会保存半截译注，也不会发 completed。
- 所有 chunk 成功后，后端按 `chunk.index` 排序合并完整译注。
- 后端从合并后的 `[[word|翻译|pos]]` 标记中提取 vocabulary 和词性；旧 `[[word|翻译]]` 标记仍兼容，词性回退为 `other`。
- 译注 prompt 使用 block-based context：稳定 system policy 放在 system prompt；每次请求的 `density_profile`、`mastered_words`、`reader_text` 放在 user prompt。
- 译注 prompt 支持 `beginner/intermediate/advanced` 三档密度；前端 UI 显示为 `H/M/L`。
- 生成译注时会从 SQLite 读取已掌握词，注入 `mastered_words` block，避免模型再次标注这些词。

`LazyAnnotatorService` 用于延迟创建真实 provider，让没有配置 API key 的情况下仍然可以启动后端、浏览 corpus、查看已生成数据。

### `src/superhp_agent/services/lookup.py`

`WordLookupService` 是查词服务。它可以看作阅读流程之外的插件能力。

它不应该由主 Router 直接管理，因为查词更像用户在阅读界面中的局部辅助动作，而不是“下一步阅读流程”的核心状态转移。

当前查词 API 返回：

- `word`
- `word_cn`
- `pos`
- `sentence_cn`

手动添加生词时会关联当前 `unit_id`，保存上下文和词性，并把词条重新置为未掌握。

## 工具层

### `src/superhp_agent/tools/`

工具层把部分后端能力包装成 agent tool。

当前阅读工具包括：

- 列出阅读单元。
- 按 id 读取一个阅读单元。

这些工具仍然通过 `CorpusStore` 读取文本，因此继承了 corpus 的路径边界限制。也就是说，工具可以使用 corpus，但不能绕过 corpus 去读任意文件。

## Prompt 与 Schema

### `src/superhp_agent/prompts.py`

集中存放译注、查词等 LLM 任务的 prompt 构造逻辑。

### `src/superhp_agent/schemas.py`

定义 API 和 WebSocket 事件会使用的 Pydantic schema。

schema 是后端和前端之间的契约。字段命名里还保留了一些 `chapter_id` 兼容字段，是为了让旧测试和旧前端迁移更平滑；新的核心概念应优先使用 `unit_id`。

## 一次典型阅读流程

1. 前端建立 WebSocket 连接。
2. `ReadingSocketSession` 发送 `ready`。
3. `ReadingFlowRouter` 读取当前状态并返回 cards。
4. 用户点击一个 card action。
5. WebSocket session 把 action 交给 `ActionDispatcher`。
6. 对应 handler 读取 corpus、写 memory、调用 annotator 或读取译注副本。
7. 生成译注时按 `level` 写入 level-specific annotated copy，并写入 vocabulary DB。
8. 后端通过 WebSocket 推送进度和结果。
9. action 完成后重新生成 cards，等待用户下一次选择。

## 后续扩展建议

- 新增阅读流程选项：优先改 `cards.py` 和 `action_dispatcher.py`。
- 新增状态判断：优先改 `reading_state.py`，再让 router 使用它。
- 新增模型能力：优先加 service，不要直接在 transport 或 router 中调用 provider。
- 新增进度回传：优先通过 `EventSink` 发事件，不要让服务层直接依赖 WebSocket。
- 新增工具：通过 tools 层包装已有能力，避免工具绕过核心边界。
- 新增持久化数据：先判断是流程状态还是可查询数据，再决定放 memory 还是 SQLite。
