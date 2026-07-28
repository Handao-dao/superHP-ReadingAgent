# 阅读伴侣 Agent：长期会话、情景记忆与阅读检索设计

> 状态：首批 Contract 已建立，尚未替换当前运行中的 `RecommendationAgentSession`。
>
> 本文定义后续演进方向。第一阶段只稳定边界和 Contract，不立即扩大工具权限，也不改变现有
> 译注、查词和阅读监控主链路。

## 1. 定位变化

当前实现以“选书 Agent”为中心，主要服务初次推荐和阅读困难后的再次推荐。后续产品入口允许
用户在阅读过程中随时呼出同一个智能体，因此更合适的定位是：

> 阅读伴侣是长期存在的对话 Agent；图书推荐只是它的一项能力。

三个明确入口复用同一个 Agent Loop：

```text
初次使用
    → 了解偏好并推荐起始书籍

阅读中主动呼出
    → 讨论当前图书、章节、人物和阅读体验

连续阅读困难
    → 继承历史与近期证据，分析后继续支持或重新推荐
```

智能体可以观察当前阅读状态、决定直接回答还是调用工具，并根据工具结果继续对话；它不能绕过
现有 Router、Policy 和用户授权，直接修改阅读数据或执行换书等副作用。

## 2. 第一阶段能力边界

### 2.1 支持

- 延续初次选书和再次推荐对话；
- 回顾用户已经读过的情节；
- 梳理人物、关系、动机和当前章节；
- 回答用户针对选中文本提出的问题；
- 讨论阅读困难来自词汇、句法、背景知识还是叙事结构；
- 建议继续阅读、调整辅助或重新选书；
- 在用户明确选择后记录推荐结果。

### 2.2 暂不支持

- 未经确认直接修改译注目标、书签、进度和词汇状态；
- 自动下载、导入、删除或切换图书；
- 读取当前进度之后的正文；
- 把模型推测直接写成长期用户事实；
- 为体现 Agent 形式而复制现有 Annotator、Lookup 或 Reading Policy。

## 3. 入口与前端交互

阅读页增加长期可见的“阅读助手”入口，适合使用侧边对话抽屉，避免离开正文或丢失分页位置。
打开抽屉本身不调用模型，可以根据当前状态展示快捷问题：

- 聊聊这本书；
- 帮我理清这一章；
- 我有点看不懂；
- 这本书适合我吗；
- 我想换一本。

用户选中正文后，可以通过“问问助手”把选中片段放入本轮 Invocation Context。

关闭抽屉只表示暂时隐藏界面，不结束当前交流。手动交流由显式“结束本次交流”结束；推荐场景还
可以在用户选书、决定继续当前图书或放弃本轮推荐时自然结束。

## 4. 长期 Session 与 Episode

### 4.1 Session

`ReadingCompanionSession` 表示智能体与当前读者的长期关系，不绑定某一本书或某一次推荐：

```text
ReadingCompanionSession
    ├── Episode 1：初次选书
    ├── Episode 2：阅读中讨论人物
    ├── Episode 3：讨论当前章节
    ├── Episode 4：阅读困难后的再次推荐
    └── Episode 5：换书后的后续交流
```

当前项目是单用户原型，可以使用稳定的默认 `reader_key`。文本 `profile_id` 表示英文、文言文等
阅读场景，不等于用户身份，不能把它直接当作长期会话的读者主键。未来增加多用户时再引入正式
`reader_id`。

Session 只有 `active` 和 `archived` 这类长期状态。选定一本书只结束当前推荐 Episode，不终止
整个 Session。

### 4.2 Episode

Episode 表示一次具有明确触发原因和结束边界的交流：

```text
trigger
    onboarding
    manual_reading
    difficulty_alert
    user_request

state
    active
    completed
    abandoned
```

Episode 开始时冻结一份轻量调用现场：

- 当前 `book_id`；
- 当前 `chapter_id` 和阅读位置；
- 触发原因；
- 用户选中的文本；
- 阅读困难场景中的聚合证据；
- 本轮开始消息位置。

这些数据描述“为什么此时呼出助手”，不会随之后的页面跳转悄悄改变。最新阅读状态仍可在每次
模型调用前作为动态 Context 注入。

推荐过程的 `searching / presented / selected` 属于 Episode 内部任务状态，不再承担整个长期
Session 的生命周期。

### 4.3 Episode 结束条件

可以结束当前 Episode 的事件包括：

- 用户点击“结束本次交流”；
- 初次或再次推荐中明确选定图书；
- 用户明确决定继续当前图书并结束换书讨论；
- 用户主动放弃本次任务；
- 切换到另一部图书，需要开启新的阅读现场。

网络中断、Provider 失败、关闭抽屉和刷新页面都不自动结束 Episode。

## 5. 首批 Contract

`backend/src/superhp_agent/contracts/companion.py` 已建立首批不可变 Contract 和构造期校验。
以下结构用于稳定职责，不表示已经接入 Repository：

```python
ReadingCompanionSession(
    session_id: str,
    reader_key: str,
    status: "active | archived",
    active_episode_id: str,
    created_at: str,
    updated_at: str,
)

ReadingCompanionEpisode(
    episode_id: str,
    session_id: str,
    trigger: "onboarding | manual_reading | difficulty_alert | user_request",
    state: "active | completed | abandoned",
    book_id: str,
    chapter_id: str,
    selected_text: str,
    start_message_id: str,
    end_message_id: str,
    end_reason: str,
    created_at: str,
    ended_at: str,
)

ConversationMemory(
    memory_id: str,
    session_id: str,
    episode_id: str,
    kind: "episode_summary | rolling_compaction",
    revision: int,
    summary: str,
    source_start_message_id: str,
    source_end_message_id: str,
    status: "pending | ready | failed",
    input_tokens: int,
    output_tokens: int,
    created_at: str,
)
```

关键约束：

- 原始消息永久保留，摘要不覆盖或删除原始记录；
- Memory 必须保存覆盖的消息边界；
- 同一覆盖范围和 revision 的摘要生成需要幂等；
- Session 同一时间最多有一个 active Episode；
- 结构化选择、书籍 id 和阅读证据继续保存在 Contract 中，不能只存在于自由文本摘要。

## 6. 两种压缩机制

两种机制共用摘要器和 Memory Repository，但触发目的不同。

### 6.1 Episode 结束后的被动压缩

当 Episode 明确结束后，系统生成 `episode_summary`：

```text
Episode 完整结束
    ↓
保存 end_message_id 和 end_reason
    ↓
创建 pending Memory
    ↓
生成结构化摘要
    ↓
Memory 变为 ready
```

摘要建议包含：

```markdown
## 本轮目的
## 讨论内容
## 用户明确表达的偏好
## 形成的暂时判断
## 用户决定
## 尚未解决的问题
## 关联图书与章节
```

摘要调用失败不能阻塞用户关闭对话。原始消息仍然有效，Memory 保持 `pending` 或 `failed`，由
后台任务或下一次唤醒时重试。

### 6.2 当前 Episode 过长时自动压缩

每次调用 Provider 前估算模型工作 Context；接近安全阈值时创建 `rolling_compaction`：

```text
Context 接近阈值
    ↓
选择较早的完整 Turn
    ↓
上一版 Rolling Summary + 新进入压缩区间的消息
    ↓
生成下一 revision
    ↓
保留近期完整 Turn 后继续模型调用
```

自动压缩遵循：

1. 不拆开 Assistant Tool Call 与对应 Tool Result；
2. 不在正在执行的工具中间切分；
3. 为下一次模型输出和工具结果预留空间；
4. 保留最近若干完整 Turn；
5. 超长 Tool Result 在摘要输入中先做有边界的序列化；
6. 摘要失败且仍低于硬上限时可以保守继续，达到硬上限时返回可恢复错误。

触发阈值不立即写死。先记录 Provider input token usage、Context 字符规模和压缩后规模，再根据
真实模型窗口确定安全比例。

## 7. Context 投影

模型每次看到的是工作投影，而不是数据库中的全部历史：

```text
固定身份、权限与无剧透规则
        ↓
当前阅读状态
        ↓
本次 Episode 调用现场
        ↓
相关历史 Episode Summaries
        ↓
当前 Episode Rolling Summary（如果存在）
        ↓
近期完整 user / assistant / tool Turns
```

摘要属于历史数据，不是高权限指令。注入时必须标记为 Memory，不能让旧用户文本经过摘要后获得
System Instruction 的优先级。

初期 Episode 数量较少时可以注入全部摘要；数量增长后，只选取与当前图书、触发原因和用户问题
相关的摘要。

## 8. 原始历史回溯

摘要不可避免会丢失细节，因此完整消息历史仍然是事实来源。后续可以增加只读工具：

```text
search_conversation_history
```

它按关键词、图书、Episode、章节和时间范围检索历史消息。当用户明确引用过去某次交流，而当前
摘要信息不足时，Agent 可以调用该工具恢复真实上下文。

工具只返回必要片段，并携带 `episode_id` 和消息来源；它不能修改或重写历史。

## 9. 阅读内容检索

新增只读工具：

```text
search_reading_context
```

它同时支持章节摘要和已读正文片段：

```json
{
  "summary_matches": [
    {
      "chapter_id": "chapter-5",
      "summary": "本章主要发生了……"
    }
  ],
  "source_matches": [
    {
      "chapter_id": "chapter-5",
      "excerpt": "原文片段……"
    }
  ]
}
```

使用原则：

- 情节回顾、人物关系和阅读恢复优先使用章节摘要；
- 具体措辞、动作和人物对话问题补充少量原文；
- 默认检索原文，不检索模型译注版本；
- 结果必须携带图书和章节来源；
- 后端根据可信阅读进度强制限定最大章节，模型参数不能扩大范围；
- 当前进度之后的摘要和正文均不可返回，防止剧透。

工具通过 Application Service 读取现有 Corpus 和摘要能力，不让 Agent 直接访问文件路径或
Storage Adapter。

## 10. 工具集合

第一阶段保持有限工具：

```text
search_reading_context
search_local_book_catalog
present_book_recommendations
select_recommended_book
```

后续在确有需要时再增加 `search_conversation_history`。当前阅读状态、触发来源和已知阅读证据由
ContextBuilder 直接注入，不必包装成模型工具重复读取。

普通讨论直接由模型回复；只有需要恢复正文依据或查询目录时才调用工具。

## 11. 与现有推荐实现的迁移关系

当前 `RecommendationAgentSession`、Runner、HTTP 对话页和 SQLite 持久化继续作为可运行基础，
不立即进行大爆炸式重构。

`application/recommendation_companion.py` 已提供无副作用兼容投影。它不改写或保存旧 Session，
只把当前推荐上下文周期解释为一个 Companion Episode：

| 当前推荐状态 | Companion 投影 |
| --- | --- |
| `collecting_preferences / searching / awaiting_user` | active Episode |
| `completed` 且已选书 | completed Episode，原因为 `book_selected` |
| 遗留 `failed` | abandoned Episode，原因为 `unrecoverable_error` |

旧 `session_id` 继续作为长期 Session id；`context_start_index` 生成当前 Episode 起点；旧消息按
`session_id + message index` 生成稳定迁移游标。困难 Handoff 必须带可信的当前图书，否则拒绝
投影。Episode 完成或放弃后，长期 Session 仍保持 active。

建议按以下顺序迁移：

1. 已完成：新增本文 Contract，但不替换现有接口；
2. 已完成：将当前一次推荐纯投影为一个 Recommendation Episode；
3. 把 Session 的长期状态与推荐任务状态分开；
4. 让选书完成只结束 Episode，长期 Session 保持 active；
5. 增加手动阅读入口和 `search_reading_context`；
6. 接入 Episode 结束摘要；
7. 记录真实 token 数据后再接入自动 Rolling Compaction；
8. 最后增加历史消息检索和稳定偏好记忆。

现有 `context_start_index` 可以继续作为迁移期工具协议边界；进入 Episode 模型后，由稳定
`message_id` 和 Episode 消息范围替代数组下标。

## 12. 持久化建议

长期形态仍统一落在 SQLite：

```text
reading_companion_sessions
reading_companion_episodes
reading_companion_messages
conversation_memories
```

第一轮迁移可以继续把消息保存在 Session JSON 中，避免同时重构 Loop 与存储。只有当 Episode
摘要、按历史范围检索和消息数量增长成为真实需求时，再把消息拆为独立表。

## 13. 已确定的设计决策

- 阅读伴侣是长期 Agent，推荐是其能力之一；
- 当前单用户原型使用一个长期会话，不把文本 Profile 当作用户身份；
- 每个明确触发点开启一个 Episode；
- 关闭抽屉不结束 Episode；
- Episode 结束后生成被动摘要；
- 当前 Episode 过长时进行自动 Rolling Compaction；
- 两类摘要都不删除原始对话；
- 摘要不足时允许回查原始消息；
- 阅读检索同时支持章节摘要和已读正文；
- 无剧透边界由后端数据访问范围强制保证；
- 第一阶段不允许 Agent 未经确认修改阅读状态。

## 14. 下一步

首批边界进度：

1. 已完成：Session、Episode、Memory Contract 与纯状态测试；
2. 已完成：`search_reading_context` 请求、结果和无剧透范围 Contract；
3. 已完成：现有 Recommendation Session 到 Episode 的无副作用兼容投影；
4. 下一步：实现读取章节摘要与已读原文的 Application Service；
5. 下一步：在不替换现有推荐接口的前提下建立长期 Session 状态协调器；
6. 暂不接入摘要模型调用、SQLite migration 和前端按钮。

下一批优先实现阅读内容检索 Service，因为它可以独立验证摘要、正文和无剧透边界，不要求先迁移
整个推荐会话的持久化模型。
