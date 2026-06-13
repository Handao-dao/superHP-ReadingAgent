# 评测样本生成任务 Prompt

你是一个英文阅读助手项目的数据标注员。请为“点击查词”功能构造一批高质量评测样本。

## 项目背景

目标任务：

```text
输入：一个英文单词 word + 该单词所在英文句子 sentence
输出：该单词在上下文中的中文释义 word_cn、整句中文翻译 sentence_cn、词性 pos
```

这个评测集用于测试本地小模型是否能完成上下文词义消歧。请注意：这是评测集，不是训练集。样本要准确、多样、可人工检查。

## 输出格式

请只输出 JSONL，每行一个 JSON 对象，不要输出 Markdown、解释、编号列表或代码块。

每行格式：

```json
{"id":"eval-0001","word":"fine","sentence":"The wand was made of fine yew wood.","gold":{"word_cn":"优质的","pos":"adjective","sentence_cn":"这根魔杖由优质紫杉木制成。"}}
```

字段要求：

- `id`：从 `eval-0001` 开始递增。
- `word`：只允许单个英文单词，不允许词组，不允许带空格。
- `sentence`：包含该 `word` 的自然英文句子。
- `gold.word_cn`：该单词在当前上下文中的中文释义，尽量简短，优先 1-4 个汉字，必要时可稍长。
- `gold.pos`：只能是 `noun`、`verb`、`adjective`、`adverb`、`other`。
- `gold.sentence_cn`：整句自然中文翻译。

禁止输出：

- 不要输出 `phrase` 词性。
- 不要生成词组查询样本，例如 `look up`、`in charge of`、`picked up`。
- 不要输出 `sense`、`note`、`explanation` 等额外字段。
- 不要输出无法被 `json.loads` 解析的内容。
- 不要使用中文引号或尾随逗号。

## 样本设计目标

请生成 50 条样本，覆盖以下分布：

- `noun`：约 12 条
- `verb`：约 12 条
- `adjective`：约 10 条
- `adverb`：约 8 条
- `other`：约 8 条

语义类型要覆盖：

- 多义词：同一个词在不同句子中有不同意思，例如 `charge`、`fine`、`issue`、`fair`、`bound`、`present`、`object`、`figure`、`scale`、`spell`。
- 小说阅读常见词：描述动作、情绪、环境、物品、魔法相关事物。
- 容易误译词：表面常见但上下文含义不同的词。
- HP 风格但不要直接大段引用受版权保护文本；可以构造类似英文小说语境的原创句子。

## 质量要求

1. `sentence` 必须自然，像英文小说句子。
2. `word` 必须真实出现在 `sentence` 中，大小写可以不同，但拼写应一致。
3. `word_cn` 必须对应当前上下文，不要给最常见但不适用的义项。
4. `sentence_cn` 必须与英文句子语义一致，并体现该单词的上下文含义。
5. `pos` 必须标注目标单词在句子中的实际词性。
6. 避免非常生僻、模型完全无从判断的专有名词。
7. 不要让所有句子都太短；应有短句、中等句、稍复杂句。

## 输出前自检

在最终输出前，请逐行自检：

- 是否是合法 JSONL？
- 是否正好 50 行？
- 是否没有 Markdown 代码块？
- 是否所有 `word` 都是单个英文单词？
- 是否所有 `pos` 都在允许集合内？
- 是否没有 `phrase`？
- 是否没有额外字段？
- 是否 `word_cn` 和 `sentence_cn` 真的匹配上下文？
