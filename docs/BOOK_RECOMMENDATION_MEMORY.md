# 选书 Agent 的上下文压缩与记忆规划（早期方案）

> 本文是后续规划，不表示压缩器和长期记忆已经接入运行主链路。
>
> 阅读助手现已规划为跨多次触发长期存在的 Reading Companion。Session、Episode、被动摘要、
> 自动 Rolling Compaction 和历史回溯的总设计以
> [`READING_COMPANION_AGENT.md`](READING_COMPANION_AGENT.md) 为准。本文保留选书 Agent 阶段的
> 技术背景，其中“完整历史不删除、完整 Turn 切分、预留输出空间和摘要 revision”等原则继续
> 有效，但 `RecommendationContextMemory` 不再是最终命名。

## 1. 为什么需要这项能力

选书 Agent 会保留真实的 user / assistant / tool 对话，以便用户反复调整条件、恢复旧会话，并在
阅读困难后重新唤醒同一段交流。随着“换一批、解释候选、再次推荐”的次数增加，完整消息历史会
逐渐占用更多模型上下文。

目标不是删除历史，而是区分两种数据：

```text
完整 Session 历史
    事实记录、恢复与诊断依据；始终持久化，不被摘要覆盖

模型工作上下文
    摘要记忆 + 最近若干完整 turn；可以按边界投影和压缩
```

## 2. 参考 Pi Agent，但保持适合本项目的规模

Pi 的 Compaction 提供了几条适合复用的原则：

1. 达到上下文阈值时才压缩，并为下一次模型输出预留空间；
2. 从旧消息中选择压缩区间，近期消息保持原样；
3. 优先在完整 turn 边界切分，不把 Tool Call 和对应 Tool Result 拆开；
4. 保存摘要和“从哪条消息开始保留”的边界，而不是覆写原始记录；
5. 再次压缩时，把上一版摘要与新进入压缩区间的消息一起迭代；
6. 用独立的一次模型调用生成摘要，并记录该调用的 usage；
7. 序列化摘要输入时限制超长 Tool Result，防止压缩请求本身再次膨胀。

本项目没有分支树、文件操作跟踪和通用扩展 Hook，因此不复制 Pi 的 Branch Summary、树导航和
通用 Harness。第一版只需要线性 Session Compaction。

## 3. 建议的数据模型

建议通过独立 Repository 保存压缩记录，仍落在统一 SQLite 中：

```text
RecommendationContextMemory
    session_id
    revision
    summary
    summarized_through_index
    recent_context_start_index
    estimated_characters_before
    estimated_tokens_before
    summary_usage
    created_at
```

关键约束：

- 原始 `RecommendationAgentSession.conversation` 不删除；
- 一次压缩追加一个新 revision；
- ContextBuilder 只读取当前有效 revision；
- `summarized_through_index` 明确摘要覆盖范围；
- 精确 `catalog_id`、当前展示批次和最终选择继续使用结构化 Session 字段，不能只依赖模型摘要。

## 4. 摘要内容

选书 Agent 不需要通用编码任务那样的文件清单。建议使用面向阅读的稳定结构：

```markdown
## 当前目标

## 稳定题材偏好

## 难度与阅读体验

## 已展示或拒绝的方向

## 已作出的决定

## 尚未回答的问题

## 继续对话所需的关键事实
```

摘要是历史事实的压缩投影，不是新的系统指令。注入 Context 时应继续放在 metadata 区域，并标记
为不可信指令来源，防止旧用户文本经摘要后获得更高权限。

## 5. Context 组织方式

压缩后的模型输入建议为：

```text
稳定 System Rules
        ↓
当前 RecommendationRequest 与运行时结构化状态
        ↓
RecommendationContextMemory.summary
        ↓
最近若干完整 user / assistant / tool turns
```

压缩切点不能落在 Tool Result 上。一个 turn 从用户消息开始，包括随后所有 Assistant 回复、
Tool Call 和 Tool Result，直到下一条用户消息。

## 6. 触发策略

第一版不要仅凭消息条数触发。建议先记录每轮：

- Context 字符数；
- Provider 返回的 input token usage（如果供应商提供）；
- 最近一次压缩后的估算规模；
- 压缩次数。

有足够实际数据后再确定阈值。形式上可以采用：

```text
estimated_context_tokens
    > model_context_window - reserved_output_tokens
```

同时保留最近若干完整 turn，避免刚发生的候选展示、用户反馈和 Tool Result 被立即压缩。

## 7. 压缩记忆与长期用户记忆的区别

两者不要混为一个自由文本字段：

```text
Session Compression Memory
    只服务当前会话的上下文缩短，可以反复生成新 revision

Reader Preference Memory
    跨会话保存稳定偏好，例如明确喜欢的题材、长期不接受的内容和已验证的难度区间
```

未来可以从 Session 摘要中提出“记忆候选”，但只有用户明确表达或长期阅读事实反复验证后，才写入
跨会话 Reader Preference Memory。模型的一次推测不能直接升级为长期事实。

## 8. 分步实施顺序

1. 已完成：记录每次模型请求的 Context 字符规模；
2. 已完成：Handoff 保留可见对话，但隔离旧 Tool 协议轨迹；
3. 增加 Provider input token usage 统计；
4. 建立 `RecommendationContextMemory` Contract、Repository 与 SQLite 表；
5. 实现完整 turn 切点选择和摘要输入序列化；
6. 实现手动压缩，验证摘要质量和恢复一致性；
7. 最后再接入阈值触发的自动压缩；
8. 在压缩稳定后，另行设计跨 Session 的 Reader Preference Memory。
