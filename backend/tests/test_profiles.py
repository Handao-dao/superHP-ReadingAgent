from superhp_agent.profiles import (
    ClassicalChineseProfile,
    EnglishNovelProfile,
    create_default_registry,
)


def test_default_profile_registry_returns_english_novel():
    registry = create_default_registry()

    profile = registry.get()

    assert profile.id == "english_novel"
    assert profile.renderer_hint == "english_novel"
    assert registry.get("missing").id == "english_novel"
    assert registry.get("classical_chinese").id == "classical_chinese"


def test_english_novel_profile_parses_legacy_markers():
    profile = EnglishNovelProfile()

    items = profile.parse_annotation_items(
        "a [[wand|魔杖|noun]] and another [[wand|魔杖|noun]] near a [[spell|咒语]]."
    )

    assert [(item.word, item.translation, item.pos) for item in items] == [
        ("wand", "魔杖", "noun"),
        ("spell", "咒语", "other"),
    ]


def test_english_novel_profile_builds_prompt_context():
    profile = EnglishNovelProfile()

    context = profile.build_annotator_base_context(mastered_words=["wand"], level="advanced")
    user_prompt = context.render_role("user")

    assert '<density_profile level="advanced" ui="L" density="low">' in user_prompt
    assert "<mastered_words>\n[\"wand\"]\n</mastered_words>" in user_prompt
    assert "Return only the annotated passage text." in profile.base_annotator_system_prompt


def test_classical_chinese_profile_uses_shared_marker_format():
    profile = ClassicalChineseProfile()

    items = profile.parse_annotation_items(
        "[[学而时习之|学习后按时复习它|特殊句式]]，不亦[[说|同“悦”，愉快|通假字]]乎？"
    )

    assert [(item.word, item.translation, item.pos) for item in items] == [
        ("学而时习之", "学习后按时复习它", "特殊句式"),
        ("说", "同“悦”，愉快", "通假字"),
    ]


def test_classical_chinese_profile_preserves_learning_labels():
    profile = ClassicalChineseProfile()

    items = profile.parse_annotation_items(
        "[[时|按时，名词作状语|词类活用]]，[[而|表示顺承|虚词用法]]，[[未知|解释|bad-label]]"
    )

    assert [(item.word, item.pos) for item in items] == [
        ("时", "词类活用"),
        ("而", "虚词用法"),
        ("未知", "其他"),
    ]


def test_classical_chinese_profile_builds_classical_prompt_context():
    profile = ClassicalChineseProfile()

    context = profile.build_annotator_base_context(mastered_words=["说"], level="beginner")
    user_prompt = context.render_role("user")

    assert '<density_profile level="beginner" ui="H" density="high">' in user_prompt
    assert "<mastered_words>\n[\"说\"]\n</mastered_words>" in user_prompt
    assert "文言文" in profile.base_annotator_system_prompt
    assert "[[原文字词或短语|现代汉语释义|pos]]" in profile.base_annotator_system_prompt
