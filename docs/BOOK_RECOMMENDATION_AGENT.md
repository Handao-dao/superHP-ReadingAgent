# 选书 Agent 与阅读难度闭环设计

> 状态：规划草案，尚未实现。
>
> 本文记录项目从“确定性阅读工作流”向“可选的选书 Agent”演进时的产品目标、职责边界和渐进实现路线。它不是当前运行能力说明；当前后端仍以可测试的 Router、Dispatcher 和 Service 为主。

## 1. 设计目标

项目的核心目标不是督促用户背单词，而是帮助用户找到能够长期、连续阅读的英文小说，并通过大量阅读和词汇反复出现实现自然习得。

围绕这个目标，系统形成以下闭环：

```text
首次进入选书 Agent
    → 推荐一个可能合适的起点
    → 用户选择图书
    → 标注服务提供克制的中文辅助
    → Reading Monitor 长期观察主动查词行为
    → 确定性策略按需调整后续辅助强度
    → 多个观察窗口仍显示明显困难
    → 用户决定继续挑战，或授权重新选书
    → 选书 Agent 继承真实阅读证据并再次推荐
```

第一次推荐主要依赖用户表达，置信度较低；后续推荐逐渐依赖真实阅读行为。闭环优化的不是模型输出本身，而是“读物难度、内容兴趣与用户阅读体验之间的匹配”。

## 2. 三类自动化必须分开

### 2.1 Workflow

完成步骤明确、结果边界稳定的任务，例如：

```text
读取章节 → 分块 → 构造 Context → 调用 Provider → 合并 → 保存
```

译注和查词继续由 Service 完成，不需要 Agent 自主规划。

### 2.2 Adaptive Policy

根据结构化指标做可预测的参数调整，例如：

```text
长期查词密度持续偏高
    → 下一观察阶段适度提高译注目标
```

这类问题适合确定性代码和状态机，不应为了体现“智能”而交给 LLM。

未来的 `ReadingAdaptationPolicy` 可以把默认译注目标设为每 300 词约 8 处，并在系统边界内逐步调整，硬上限为每 300 词 20 处。这里的 8 是默认目标，不是必须凑满的最低数量；简单文本允许更少。单次提高最多 2，单次降低最多 1，防止支持强度来回震荡。

### 2.3 Agent

Agent 只处理无法用一张固定决策表完整描述的开放任务：

> 在用户授权后，根据阅读证据、内容偏好和可用图书来源，自主寻找、验证并解释更合适的候选书。

Agent 可以根据中间搜索结果调整条件、淘汰候选、补充查询或向用户提问，但不能绕过用户确认执行下载、导入、清除进度或切换当前图书等副作用。

## 3. 阅读监控基准

### 3.1 核心指标

最直接的困难信号是用户主动触发查词的频率：

```text
单章查词密度
= 有效查词点击次数 ÷ 本章英文词数 × 300

长期查词密度
= 观察窗口内有效查词点击总数 ÷ 观察窗口英文词数 × 300
```

统一使用“每 300 词查词多少次”表达，便于和译注密度比较。

总点击次数是主要指标，同时记录以下解释性指标：

- 不同查词项数量；
- 重复查词次数；
- 已有译注词的进一步查询次数；
- 未译注词的查询次数；
- 当前实际译注密度；
- 当前译注目标。

前端或事件处理层应过滤明显重复事件，例如同一阅读单元、同一词项在极短时间内连续触发的相同请求。重新阅读产生的查词应归属新的阅读尝试，避免和首次阅读无边界累加。

### 3.2 长期观察窗口

单章数据只形成一次 Observation，不直接得出“书籍不合适”的结论。第一版建议在同时满足以下条件后才允许判断：

```text
至少跨越 3 个不同章节
且累计观察不少于 5000 个英文词
```

实现时应按不同的 `chapter_id` 计数；一个章节即使被拆成多个 `unit_id`，也不能因此提前满足长期观察条件。

暂定的宽松区间可以作为可配置参数：

```text
每 300 词查词不超过 5 次
    → 通常保持当前策略

每 300 词查词约 5～10 次
    → 继续观察，不打扰用户

每 300 词查词超过 10 次
    → 进入困难观察状态
```

这些数值是用于收集真实数据的初始产品参数，不是语言能力标准。只有多个观察窗口持续偏高，才允许展示换书提醒。

### 3.3 辅助强度也是证据

查词减少可能来自用户逐渐适应，也可能只是系统增加了译注。因此判断书籍是否合适时，需要同时观察：

```text
主动查词密度
+ 实际译注密度
+ 高强度辅助持续的阅读量
```

如果在接近每 300 词 20 处译注时仍频繁查词，或者长期依赖高强度译注才能维持阅读，都可以成为“提供更简单候选书”的依据。

## 4. 困难提醒与用户授权

监控状态建议使用明确的有限状态：

```text
NORMAL
    │ 长期指标开始偏高
    ▼
WATCHING
    │ 多个观察窗口持续偏高
    ▼
DIFFICULTY_PROMPTED
    ├── 用户选择继续
    │       ▼
    │   CONTINUE_WITH_COOLDOWN
    │
    └── 用户选择换书
            ▼
        AGENT_HANDOFF
```

推荐的用户提示为：

> 最近几章中，你主动查词的频率持续较高，阅读可能经常被打断。要继续尝试这本书，还是看看难度更合适的选择？

可以补充一条事实依据：

```text
最近约 6000 词：平均每 300 词主动查词 12 次
```

用户选项：

```text
[我仍想继续尝试]    [好的，帮我换一本]
```

选择“继续尝试”后：

- 保留当前图书和全部进度；
- 记录用户明确接受挑战；
- 不启动 Agent；
- 进入冷却期，例如继续阅读 10000 词或跨越 5 个章节后，才允许再次提醒；
- 后续可以针对这本书提高提醒边界，避免反复否定用户选择。

选择“帮我换一本”只代表授权启动推荐任务，不代表授权系统立即结束当前阅读、下载文件或切换图书。

## 5. Agent 的两种入口

同一个 `BookRecommendationAgent` 支持两种主要入口：

```python
class RecommendationOrigin(StrEnum):
    ONBOARDING = "onboarding"
    USER_REQUEST = "user_request"
    DIFFICULTY_ALERT = "difficulty_alert"
```

### 5.1 初次使用

初次使用没有真实阅读指标。Agent 通过不超过三轮的轻量对话获得：

1. 用户感兴趣的题材或作品风格；
2. 以前读过的英文小说，以及主观难度感受；
3. 本次更希望流畅阅读，还是接受一定挑战。

仅当候选结果存在明显歧义时，再补问成人/青少年内容、篇幅、年代或系列偏好。用户可以随时要求“直接推荐”，Agent 使用保守默认值继续。

建议开场：

> 我可以帮你找一本适合开始阅读的英文小说。你最近想读哪种类型？如果有特别喜欢的小说、电影或故事风格，也可以直接告诉我。

难度锚点：

> 你以前读过英文小说吗？如果有，可以告诉我书名，以及当时读起来是轻松、适中还是比较吃力。没有读过也没关系。

阅读倾向：

> 这次阅读你更希望轻松、连续地读下去，还是愿意接受一些挑战？

初次对话只建立内部的“暂定文本难度区间”，不能声称得到了用户的正式 Lexile Reader Measure。

### 5.2 阅读困难后的重新选书

用户确认换书后，Context Builder 构造结构化交接包，而不是把原始点击日志、整本正文和全部历史对话塞给 Agent：

```python
BookRecommendationHandoff(
    origin="difficulty_alert",
    current_book={
        "book_id": "...",
        "title": "...",
        "author": "...",
        "lexile_min": 900,
        "lexile_max": 900,
        "genres": ["mystery", "detective"],
        "progress": 0.23,
    },
    reading_evidence={
        "observed_word_count": 7200,
        "lookup_density": 12.1,
        "unique_lookup_density": 9.8,
        "repeated_lookup_density": 2.3,
        "actual_annotation_density": 16.0,
    },
    recommendation_goal={
        "difficulty": "lower_than_current",
        "preserve_genre_by_default": True,
    },
)
```

Agent 首先用简短、非评判性的语言汇报依据，然后默认保留当前题材、降低语言难度。用户可以在对话中继续修改年代、篇幅、内容尺度或子类型。

## 6. Lexile 的使用边界

### 6.1 用于衡量文本，不用于伪造用户测评分数

系统使用 Lexile Text Measure 作为图书之间的相对难度坐标。查词行为只能支持内部推荐区间的校准，不能直接换算成正式的用户 Lexile Reader Measure。

推荐中应使用：

```text
当前 900L 小说持续引发较高查词密度，
下一批候选暂定在 700L～850L。
```

不应使用：

```text
系统已判断你的蓝思值为 750L。
```

内部模型建议命名为 `OperationalReadingBand`，并保存置信度和证据来源。

### 6.2 第一版默认目录图书均可阅读

当前目标是验证选书 Agent 的对话、检索和反馈闭环，不建设正式图书发行目录。因此第一版只保存
中英文书名、蓝思上下限、单本/系列类型和内容题材，默认数据库中的候选都可直接进入阅读流程。
ISBN、版本认证、来源状态和可用性检查暂不进入核心模型；真正接入外部书目或授权数据时再扩展。

目录集中保存在 `backend/data/superhp.sqlite3` 的 `recommendation_catalog` 表中，不再维护一份
并行的 YAML 或 JSON 运行时目录。`genres_json` 使用稳定、可检索的英文标签，例如
`mystery`、`fantasy`、`adventure`、`school_life`、`historical_fiction`、`nonfiction`
和 `science`；每个条目最多保留三个主要标签，避免外部书目中细碎、重复的 Subject 直接扩大
Agent 的搜索空间。

`backend/scripts/import_recommendation_catalog.py` 是显式的数据维护工具，不进入应用运行主链路：

1. 读取 UTF-8 的“蓝思值 + 英文书名 + 中文书名”文本；
2. 保留原始行，修正常见拼写和作者/奖项混入标题的问题；
3. 可用公开书目搜索补充作者与主题，联网结果不覆盖用户提供的蓝思值；
4. 将外部 Subject 映射为项目自己的有限风格标签；
5. 低置信度或未匹配条目使用人工覆盖或保守标签，并写入本地审计报告；
6. 最后在单个事务中替换可重置的本地推荐目录。

批量补全优先使用 Open Library Search API，并携带标识 User-Agent、限制并发；Google Books
保留为可选来源。两者只作为题材和作者的辅助元数据来源，不作为 Lexile 数据来源，也不在
用户阅读或 Agent 对话期间实时调用。

公开元数据接口说明：

- [Open Library Search API](https://openlibrary.org/dev/docs/api/search)
- [Open Library API 使用说明](https://openlibrary.org/developers/api)
- [Google Books Volumes API](https://developers.google.com/books/docs/v1/reference/volumes/list)

### 6.3 不自动抓取 Find a Book 网页

Lexile Find a Book 可以作为用户手动查询入口和产品设计参考，但 MetaMetrics 当前使用条款禁止机器人或其他自动化方式访问站点，因此不能把自动点击或抓取网页直接包装成 Agent 工具。

相关官方资料：

- [Lexile Find a Book](https://hub.lexile.com/find-a-book/)
- [Find a Book User Guide](https://hub.lexile.com/find-a-book-tool-user-guide/)
- [MetaMetrics Terms of Use](https://hub.lexile.com/terms-of-use/)
- [MetaMetrics Licensed Solutions](https://metametricsinc.com/licensed-solutions/)

渐进接入方式：

1. 当前个人项目阶段：用户手动提供查询结果，或使用本地小型图书目录；
2. 后续正式接入：购买 Lexile Titles Database API 授权；
3. Agent 始终依赖统一 Port，不感知具体数据来源。

## 7. Agent 可使用的最小工具

### `ReadingProfileReader`

读取结构化阅读事实：

- 当前和历史阅读图书；
- 长期查词趋势；
- 已接受或拒绝的推荐；
- 题材、篇幅和内容偏好；
- 推荐后的真实阅读结果。

### `BookCatalogSearchTool`

这是实际暴露给 Agent 的只读工具。它接收 JSON 友好的蓝思上下限、风格标签、条目类型、
排除 id 和结果数量，返回候选及匹配证据：

```python
await search_local_book_catalog(
    lexile_min=500,
    lexile_max=700,
    genres=["mystery", "adventure"],
    entry_kinds=["book", "series"],
    excluded_ids=["current-book"],
    limit=5,
)
```

第一版只返回严格匹配，不会在无结果时静默扩大蓝思区间或删除题材条件。Agent 可以根据空结果、
当前对话和剩余轮次，明确决定补问用户或再次调用工具；每次放宽都体现在新的工具参数中。

内部调用链为：

```text
BookCatalogSearchTool
    → RecommendationCandidateService
    → BookDifficultyCatalog Port
    → SQLiteBookDifficultyCatalog
```

`BookDifficultyCatalog` 仍是应用内部 Port，不直接作为 ToolList 暴露给 Agent。正式接入其他合法
书目来源时可以替换 Adapter，而不修改 Agent 工具参数和候选匹配 Service。

### `BookSampleAnalyzer`（后续可选）

在合法获得正文样本的前提下，补充分析句法、词汇和叙事特点。它只提供辅助证据，不能把自己的估算冒充认证 Lexile Measure。

## 8. Agent Loop 与停止条件

Agent 的推荐循环为：

```text
读取推荐请求和阅读状态
    → 形成初始难度与题材条件
    → 查询目录
    → 比较单本/系列类型、蓝思区间和内容偏好
    → 淘汰不合适候选
    → 候选不足时显式调整下一次工具参数或向用户补问
    → 得到足够候选后排序并解释
```

建议的停止条件：

- 找到 2～3 本来自本地数据库的候选；
- 候选难度和题材满足当前目标，或已明确标记偏离项；
- 候选不是用户已经拒绝的同一目录条目；
- 系列范围不冒充具体单本的精确蓝思值；
- Agent 可以解释每本书为什么被推荐；
- 如果数据不足，明确返回缺失信息，而不是凭模型记忆编造书目或 Lexile 数值。

首批结果建议分为：

```text
首选推荐
更轻松的选择
稍有挑战的选择
```

用户后续可以：

```text
[阅读样章] [选择这本] [不感兴趣] [换一批] [调整条件]
```

## 9. 推荐结果与长期记忆

用户点击“选择这本”只表示接受候选，不代表推荐已经成功。推荐结果需要经过实际阅读验证：

```python
RecommendationOutcome(
    recommendation_id="...",
    selected_book_id="...",
    observed_word_count=7200,
    lookup_density=4.8,
    completed_unit_count=4,
    continued_reading=True,
    outcome="good_fit",
)
```

结果至少区分：

- `good_fit`：难度与兴趣表现均较稳定；
- `difficulty_mismatch`：长期查词或辅助依赖仍然过高；
- `interest_mismatch`：难度可能合适，但用户很快放弃或明确不喜欢；
- `availability_problem`：版本、语料或导入存在问题；
- `unknown`：阅读量不足，无法判断。

事实和模型判断分开存储：

```text
阅读事实
    查词事件、阅读量、完成度、用户选择、实际译注密度

暂时判断
    当前书可能偏难、偏好某类题材、推荐区间需要下移
```

Agent 每次只读取聚合后的事实和可修正判断，不依赖无限增长的对话全文。

## 10. 与现有后端分层的关系

```text
Reading Monitor / Adaptation Policy
    │ 产生长期困难状态
    ▼
Flow Router
    │ 展示“继续尝试 / 帮我换一本”
    ├── 继续尝试
    │       └── Repository 保存选择与冷却状态
    │
    └── 帮我换一本
            ▼
        Dispatcher 创建推荐任务
            ▼
        Context Builder 构造 Handoff
            ▼
        BookRecommendationAgent
            ▼
        通过 Ports 调用阅读画像、图书目录和本地书库
```

职责边界：

- Transport 只负责传递对话消息和结构化事件；
- Flow Router 决定何时向用户展示授权选项；
- Monitor 和 Adaptation Policy 使用确定性规则；
- Dispatcher 只在用户同意后创建 Agent 任务；
- Agent 负责开放式搜索和候选验证，不直接修改阅读状态；
- Repository 保存阅读事实、用户授权、冷却状态和推荐结果；
- Composition Root 选择本地图书目录或未来的授权 API Adapter。

该扩展会增加新的入口和事件消费者，届时可以重新评估 Application Bus 是否具有实际价值；不应仅为了这份规划提前实例化通用 Bus 或 Tool Registry。

## 11. 渐进实现路线

### 阶段 1：稳定 Contracts 与 SQLite 目录

- 定义 Recommendation Request、Handoff、Candidate、Outcome；
- 定义 `BookDifficultyCatalog` Port；
- 用 SQLite 统一保存中英文书名、蓝思区间、条目类型和内容题材；
- 导入用户提供的本地图书数据进行测试；
- 暂不接入外部 API，也不修改当前阅读流程。

### 阶段 2：初次选书 Agent

- 实现最多三轮的渐进式初次对话；
- 从本地目录查询和验证候选；
- 返回三本带依据的推荐；
- 用户确认后进入现有图书和标注流程。

### 阶段 3：阅读监控与困难提醒

- 记录有效查词事件和阅读尝试；
- 聚合每章与长期窗口指标；
- 实现 NORMAL、WATCHING、PROMPTED 和 COOLDOWN 状态；
- 用户确认换书后生成结构化 Handoff。

### 阶段 4：推荐结果反馈

- 记录推荐选择和后续阅读表现；
- 区分难度不匹配与兴趣不匹配；
- 让下一次 Agent 会话读取过去推荐结果；
- 用真实数据校准观察窗口和阈值。

### 阶段 5：正式目录接入

- 在获得许可后实现 Lexile Titles Database API Adapter；
- 保留本地目录作为测试替身和离线 fallback；
- 增加限流、缓存、来源追踪和失败降级；
- 不改变 Agent 和 Application 层所依赖的 Port。

## 12. 当前明确不做

- 不让 LLM 代替可测试的查词密度计算和阈值状态机；
- 不把查词行为宣传成正式用户 Lexile 测评；
- 不自动抓取 Lexile Find a Book 网页；
- 不让 Agent 未经确认下载、导入、删除或切换图书；
- 不把自动译注词汇等同于用户明确加入的个人生词；
- 不强制用户背单词或完成复习任务；
- 不为了 Agent 形式提前重构稳定的 Annotator、Lookup 和 Storage 主链路；
- 不在第一版同时引入通用 Planner、长期自由记忆和无限工具权限。
