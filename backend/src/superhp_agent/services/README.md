# Service 层说明

本文记录 `services/` 内业务服务的职责边界和运行语义。项目整体分层见上一级
[`README.md`](../README.md)，后端功能总览见 [`BACKEND_OVERVIEW.md`](../../../BACKEND_OVERVIEW.md)。

## 职责边界

Service 负责完成一个明确的后端业务任务，例如译注生成和上下文查词。它可以组合
Profile、Context 和 Provider Port，但不负责：

- 接收 HTTP 或 WebSocket 消息。
- 决定阅读流程和前端 Cards。
- 直接操作 SQLite、Memory 或译注文件。
- 把模型返回错误直接拼成 Transport 协议。

Provider 负责模型 SDK、请求参数和瞬时错误重试；Service 负责判断最终模型结果在当前业务中
是否可用，并以 Contracts 中的结构化结果向上层传递状态。

## 英文译注 Context 组织

英文小说是当前产品主路径。译注 Context 按稳定规则、整章任务状态和当前 chunk 数据组织：

```text
System / Static
    system_policy
    annotation_contract
    annotation_examples
    mastered_words_policy
    output_contract

User / Chapter Task
    density_profile
    mastered_words

User / Chunk Data
    reader_text
```

熟词策略属于稳定 system 指令；动态熟词 JSON 和 Density 属于整章任务数据；每个并发请求只在
基础 Context 末尾追加自己的 `reader_text`。Density 百分比是软指导，真实阅读难度优先于凑齐
数值配额。Prompt 对原文保持的要求与后端校验一致：移除 marker 后必须逐字符等于输入。

## AnnotatorService 的两层兜底

译注以单个 chunk 为独立模型任务。每个 chunk 的处理流程如下：

```text
单个 chunk
    ↓
Provider 调用与 retry
    ├── 最终失败 → 原文回退，provider 类警告
    └── 返回内容
            ↓
        格式和原文校验
            ├── 不合规 → 原文回退，validation 类警告
            └── 合规 → 使用译注
```

第一层由 Provider 提供，解决网络超时、限流和临时服务错误。重试耗尽后，Service 不让一个
chunk 阻断整章，而是使用该 chunk 的原文，并生成：

```text
category = provider
code = provider_failed
```

第二层由 Profile 校验器提供，解决模型虽然成功返回、但内容不可信的问题。校验器要求新生成
结果使用三字段 `[[原文|翻译|pos]]` 标记，将所有标记还原成左侧原文，并与输入 chunk 精确比较。
标记损坏、POS 非法、输出为空或截断、正文被增删改时，Service 同样回退原文，并生成
`validation` 类问题，例如：

```text
malformed_marker
invalid_pos
source_mismatch
empty_output
truncated_output
```

降级信息使用 `contracts/annotation.py` 中的 `ServiceIssue`、`AnnotationChunkOutcome` 和
`AnnotationResult` 传递。Service 同时发送 `annotation.degraded` 事件，事件包含稳定的
`category`、`code` 和 `chunk_index`；前端不应依赖可变的错误文案判断类型。

## 已掌握词动态筛选

已掌握词不会再整表加载并复制到每个 Prompt。Dispatcher 在 Provider 并发开始前先对整章做
一次轻量候选提取，再通过 `VocabularyRepository.find_mastered_words()` 批量查询当前语言
下真正出现在本章的已掌握词：

```text
整章原文
    → 提取英文单词/短语与中文短片段
    → 分批查询 SQLite（每批最多 400 个候选）
    → 得到本章相关已掌握词
    → AnnotatorService 为整章构造一份基础 Context
    → 所有 chunk 共用本章相关 mastered_words
    → 并发调用 Provider
```

SQLite 查询不进入并发 chunk 区域，因此不会让 8 个模型任务争用数据库锁。行为日志中的
`annotation_mastery_prepared` 记录候选数、命中数和准备耗时，便于用真实章节评估本地筛选成本。
候选器是检索用途的轻量规则，不承担完整语言学分词：当前支持最多四个英文词的连续短语，以及
最多四个连续中文字符的片段。当前单章最多约 8 个 chunk，因此不再为每个 chunk 重复提取和
筛选；若真实日志显示单章命中规模显著增长，再评估恢复更细粒度的筛选。

## 合并与持久化

- 校验通过和降级后的 chunk 都按原始 `index` 合并，因此前端始终能获得完整可读文本。
- 部分 chunk 降级时，Dispatcher 可以保存混合译注，并把完成状态标为 `degraded`。
- 全部 chunk 降级时，只向前端返回原文，不创建译注副本，也不标记为已译注，便于用户稍后重试。
- 取消请求和未分类的程序异常不属于业务降级，仍然向上抛出，并取消、等待其余并行任务退出。

这里的原则是：模型或格式问题不能破坏阅读体验，但程序错误也不能被宽泛异常捕获静默隐藏。
