"""Classical-Chinese prompts, labels, validation, and marker parsing policy."""

from __future__ import annotations

import json
import re

from superhp_agent.context import ContextBlock, ContextBundle
from superhp_agent.contracts.annotation import AnnotationItem, ServiceIssue
from superhp_agent.profiles.base import CardCopy
from superhp_agent.profiles.validation import validate_annotation_output

# These learning labels are Profile policy, not generic backend POS values.
# New output is strict; the parser still normalizes aliases in saved old data.
ANNOTATION_POS = frozenset(
    {"重点实词", "重点虚词", "通假字", "古今异义", "词类活用", "虚词用法", "特殊句式", "其他"}
)

SYSTEM_POLICY = """
你是一名专业的中文文言文学习助手，面向正在学习古文的现代汉语读者。
你的任务是在尽量保留原文阅读体验的前提下，标出真正影响理解和考试分析的重点字词、短语和句式。
""".strip()

ANNOTATION_CONTRACT = """
输入：一段文言文原文。
输出：同一段文言文原文，只把需要解释的重点字词、短语或句式替换为行内标注。

除被替换为标注的片段外，必须尽量保持原文不变。
不要改写、扩写、删减、概括、重排或直接输出整段现代汉语译文。
尽量保留原文段落、标题、换行、标点和字序。

行内标注格式：[[原文字词或短语|现代汉语释义|pos]]
竖线左侧必须使用原文中的确切字词或短语。
不要在原文、释义或 pos 字段中使用竖线 |。
现代汉语释义必须贴合上下文，优先使用简洁解释；必要时可解释为句式功能或语法作用。
pos 必须是以下中文学习标签之一：重点实词、重点虚词、通假字、古今异义、词类活用、虚词用法、特殊句式、其他。
如果标注对象是特殊句式、固定结构或整句片段，pos 应优先使用“特殊句式”。
如果标注对象是普通短语或概括性理解单元，且不属于上述具体标签，pos 才使用“其他”。
不要输出英文词性，如 noun、verb、adjective、phrase。

优先标注：
1. 影响句意的重点实词、虚词。
2. 古今异义、一词多义、通假字。
3. 词类活用，如名词作动词、形容词作动词、使动、意动。
4. 固定结构和特殊句式，如判断句、被动句、省略句、倒装句。
5. 需要现代汉语转换才能理解的短语。

如果短语或句式才是真正难点，应整体标注短语，而不是拆成多个单字。
不要为凑密度标注过于简单、上下文已经显然的字词。
不要在标注前后重复原文字词。
正确："[[说|同“悦”，愉快|通假字]]"
正确："[[学而时习之|学习后按时复习它|特殊句式]]"
正确："[[时|按时，名词作状语|词类活用]]"
正确："[[而|表示顺承|虚词用法]]"
错误："学[[学|学习|verb]]而时习之"
错误："学而时习之[[学而时习之|学习后按时复习它|特殊句式]]"
""".strip()

ANNOTATION_EXAMPLES = """
输入：
学而时习之，不亦说乎？

较好输出：
[[学而时习之|学习后按时复习它|特殊句式]]，不亦[[说|同“悦”，愉快|通假字]]乎？

较差输出：
学[[学|学习|verb]]而时[[时|按时|adverb]]习之，不亦说[[说|愉快|adjective]]乎？
原因：把整体理解单元拆得过碎，且使用英文标签并重复原文字词，破坏阅读体验。
""".strip()

OUTPUT_CONTRACT = """
只返回带行内标注的文言文原文。
不要输出 JSON。
不要输出词汇表。
不要使用代码块。
不要在原文前后添加讲解、标题、总结或整段译文，除非这些内容本来就在输入中。
""".strip()

MASTERED_WORDS_POLICY = """
不要标注 mastered_words 中列出的字词或短语。
如果 mastered_words 是空 JSON 数组，则忽略本规则块。
""".strip()

ANNOTATION_SYSTEM_BLOCKS = (
    ContextBlock("system_policy", SYSTEM_POLICY, role="system"),
    ContextBlock("annotation_contract", ANNOTATION_CONTRACT, role="system"),
    ContextBlock("annotation_examples", ANNOTATION_EXAMPLES, role="system"),
    ContextBlock("output_contract", OUTPUT_CONTRACT, role="system"),
)

BASE_ANNOTATOR_SYSTEM_PROMPT = ContextBundle(
    system_blocks=ANNOTATION_SYSTEM_BLOCKS,
).render_role("system")

LEVEL_PROFILES = {
    "beginner": {
        "ui": "H",
        "label": "文言文基础学习者，需要较高密度辅助",
        "density": "high",
        "target": "标注大多数影响理解的重点字词、虚词、活用和句式",
        "rules": (
            "面向基础学习者，标注密度可以较高。"
            "重点解释常见实词、虚词、通假字、古今异义、词类活用和固定句式。"
            "遇到整句理解依赖特殊结构时，优先整体标注短语或结构。"
            "不要逐字机械标注，应保留原文阅读流畅度。"
        ),
    },
    "intermediate": {
        "ui": "M",
        "label": "有一定文言基础的学习者，需要中等密度辅助",
        "density": "medium",
        "target": "标注主要理解障碍和考试高频点",
        "rules": (
            "面向有一定基础的学习者，跳过非常基础且上下文明确的字词。"
            "集中标注影响句意的实词、虚词、古今异义、活用、固定结构和特殊句式。"
            "优先选择对翻译、断句或考点判断有帮助的片段。"
        ),
    },
    "advanced": {
        "ui": "L",
        "label": "文言文进阶学习者，只需要低密度提示",
        "density": "low",
        "target": "只标注罕见、歧义或关键考点",
        "rules": (
            "面向进阶学习者，只标注容易误解、语义有歧义、用法特殊或考点价值高的内容。"
            "常见实词、常见虚词和普通句式一般不标注。"
            "拿不准是否必要时，倾向于不标注。"
        ),
    },
}

LOOKUP_SYSTEM_PROMPT = """
# 角色
你是一名专业的文言文字词和句子翻译助手。

你的任务是根据一个文言字词及其所在句子，给出贴合上下文的现代汉语释义、中文 pos 标签，以及整句现代汉语翻译。

# 规则
1. 字词释义必须贴合上下文，不要只给字典义。
2. 释义应简洁，可说明通假、活用、古今异义或虚词功能。
3. 整句翻译应使用自然现代汉语，保留原意。
4. pos 必须是：重点实词、重点虚词、通假字、古今异义、词类活用、虚词用法、特殊句式、其他 之一。
5. 如果查询对象不是单一字词，而是短语、固定结构或整句片段，pos 优先使用“其他”。
6. 不要添加多余讲解。

# 输出规则
必须只输出有效 JSON。
不要输出 Markdown。
不要使用代码块。

# 输出格式
{
  "word": "原文字词",
  "word_cn": "现代汉语释义",
  "pos": "重点实词|重点虚词|通假字|古今异义|词类活用|虚词用法|特殊句式|其他",
  "sentence_cn": "整句现代汉语翻译"
}
""".strip()

LOOKUP_USER_PROMPT_TEMPLATE = """
字词：{word}

所在句：
<text>
{sentence}
</text>

只返回符合格式的有效 JSON。
""".strip()

CARD_COPY = CardCopy(
    empty_title="暂无研读文本",
    empty_body="请先向语料目录添加文言文 Markdown 文件。",
    start_title="准备研读",
    start_prefix="下一篇",
    complete_title="本篇完成",
    final_complete_title="全部完成",
    complete_prefix="本篇已读完。可以继续下一篇，或回看原文与注释。",
    back_to_annotated_label="回到注释文本",
    back_to_source_label="回到原文",
    learning_item_singular="重点",
    learning_item_plural="重点",
    learning_item_scope="文言知识点",
    unit_body_template="{prefix}：《{book_title}》第 {chapter_no} 篇，{chapter_title}。",
    review_body_template="{prefix} 本篇还有 {count} 个{scope}可复习。",
    generate_annotation_label="生成注释",
    open_annotated_label="读注释本",
    read_original_label="读原文",
    review_items_label="复习重点",
    start_next_label="研读下一篇",
)


class ClassicalChineseProfile:
    """Profile for classical Chinese annotation using the shared marker format."""

    id = "classical_chinese"
    language_id = "lzh"
    label = "Classical Chinese study reading"
    renderer_hint = "english_novel"
    card_copy = CARD_COPY

    @property
    def base_annotator_system_prompt(self) -> str:
        return BASE_ANNOTATOR_SYSTEM_PROMPT

    @property
    def lookup_system_prompt(self) -> str:
        return LOOKUP_SYSTEM_PROMPT

    def normalize_level(self, level: str | None) -> str:
        if level in LEVEL_PROFILES:
            return str(level)
        return "intermediate"

    def build_annotator_context(
        self,
        text: str,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
    ) -> ContextBundle:
        return self.build_annotator_base_context(
            mastered_words=mastered_words,
            level=level,
        ).with_blocks(_reader_text_block(text))

    def build_annotator_base_context(
        self,
        *,
        mastered_words: list[str] | None = None,
        level: str = "intermediate",
    ) -> ContextBundle:
        return ContextBundle(
            system_blocks=ANNOTATION_SYSTEM_BLOCKS,
            user_blocks=(
                _density_profile_block(self.normalize_level(level)),
                _mastered_words_block(mastered_words),
                _mastered_words_policy_block(),
            ),
        )

    def build_lookup_user_prompt(self, *, word: str, sentence: str) -> str:
        return LOOKUP_USER_PROMPT_TEMPLATE.format(word=word, sentence=sentence)

    def normalize_annotated_text(self, content: str) -> str:
        text = _strip_code_fence(content).strip()
        legacy_json_text = _extract_loose_annotated_text(text)
        if legacy_json_text is not None:
            text = legacy_json_text.strip()
        return text

    def validate_annotated_text(
        self,
        *,
        source_text: str,
        annotated_text: str,
    ) -> ServiceIssue | None:
        return validate_annotation_output(
            source_text=source_text,
            annotated_text=annotated_text,
            allowed_pos=ANNOTATION_POS,
        )

    def parse_annotation_items(self, text: str) -> list[AnnotationItem]:
        seen: set[str] = set()
        items: list[AnnotationItem] = []
        for match in re.finditer(r"\[\[([^|\]]+)\|([^|\]]+)(?:\|([^|\]]+))?\]\]", text):
            word = match.group(1).strip()
            translation = match.group(2).strip()
            pos = _normalize_marker_pos(match.group(3), word=word)
            key = word
            if not word or not translation or key in seen:
                continue
            seen.add(key)
            items.append(
                AnnotationItem(
                    word=word,
                    translation=translation,
                    context=_annotation_context(text, match.start()),
                    pos=pos,
                )
            )
        return items


def _density_profile_block(level: str) -> ContextBlock:
    level_profile = LEVEL_PROFILES[level]
    content = (
        f"Target reader: {level_profile['label']}\n"
        f"Target density: {level_profile['target']}\n\n"
        f"{level_profile['rules']}"
    )
    return ContextBlock(
        "density_profile",
        content,
        role="user",
        attrs={
            "level": level,
            "ui": level_profile["ui"],
            "density": level_profile["density"],
        },
    )


def _mastered_words_block(mastered_words: list[str] | None) -> ContextBlock:
    return ContextBlock(
        "mastered_words",
        json.dumps(mastered_words or [], ensure_ascii=False),
        role="user",
    )


def _mastered_words_policy_block() -> ContextBlock:
    return ContextBlock("mastered_words_policy", MASTERED_WORDS_POLICY, role="user")


def _reader_text_block(text: str) -> ContextBlock:
    return ContextBlock("reader_text", text, role="user")


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _extract_loose_annotated_text(text: str) -> str | None:
    marker = '"annotated_text"'
    start = text.find(marker)
    if start < 0:
        return None
    colon = text.find(":", start + len(marker))
    if colon < 0:
        return None
    value = text[colon + 1 :].lstrip()
    if value.startswith('"'):
        value = value[1:]

    vocab_marker = re.search(r'"\s*,\s*"extracted_vocabulary"\s*:', value)
    if vocab_marker:
        value = value[: vocab_marker.start()]
    else:
        value = re.sub(r'"\s*}\s*$', "", value, flags=re.DOTALL)
        value = re.sub(r'"\s*,\s*}\s*$', "", value, flags=re.DOTALL)

    value = value.strip()
    if not value:
        return None
    return value.replace("\\n", "\n").replace('\\"', '"')


def _annotation_context(text: str, index: int) -> str:
    left = max(
        text.rfind("。", 0, index),
        text.rfind("！", 0, index),
        text.rfind("？", 0, index),
        text.rfind(".", 0, index),
        text.rfind("!", 0, index),
        text.rfind("?", 0, index),
    )
    right_candidates = [
        pos
        for pos in (
            text.find("。", index),
            text.find("！", index),
            text.find("？", index),
            text.find(".", index),
            text.find("!", index),
            text.find("?", index),
        )
        if pos >= 0
    ]
    right = min(right_candidates) if right_candidates else min(len(text), index + 80)
    start = left + 1 if left >= 0 else max(0, index - 40)
    return re.sub(r"\s+", " ", text[start : right + 1]).strip()[:160]


def _normalize_marker_pos(pos: str | None, *, word: str) -> str:
    value = str(pos or "").strip()
    aliases = {
        "实词": "重点实词",
        "虚词": "重点虚词",
        "句式": "特殊句式",
        "特殊结构": "特殊句式",
        "活用": "词类活用",
    }
    value = aliases.get(value, value)
    return value if value in ANNOTATION_POS else "其他"
