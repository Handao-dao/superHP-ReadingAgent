from superhp_agent.profiles import (
    ClassicalChineseProfile,
    EnglishNovelProfile,
    create_default_registry,
)
from superhp_agent.profiles.english_novel import ANNOTATION_EXAMPLES


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

    context = profile.build_annotator_base_context(mastered_words=["wand"])
    user_prompt = context.render_role("user")
    system_prompt = context.render_role("system")

    assert "<density_profile" not in user_prompt
    assert "<mastered_words>\n[\"wand\"]\n</mastered_words>" in user_prompt
    assert "<mastered_words_policy>" in system_prompt
    assert "character-for-character identical" in system_prompt
    assert "English novels" in system_prompt
    assert "lexical annotation assistant" in system_prompt
    assert "Prioritize exact source preservation" in system_prompt
    assert "normally use no more than 8 annotations" in system_prompt
    assert "never exceed 15 annotations" in system_prompt
    assert "<harry_potter_selection_policy>" in system_prompt
    assert "after the general density and selection rules" in system_prompt
    assert "widely established Chinese rendering" in system_prompt
    assert "solely because it is magical, fictional, or capitalized" in system_prompt
    assert "1-4 Chinese characters" not in system_prompt
    assert "Return only the annotated passage text." in profile.base_annotator_system_prompt


def test_english_annotation_examples_cover_word_and_phrase_boundaries():
    assert "[[bewildered|困惑的|adjective]]" in ANNOTATION_EXAMPLES
    assert "[[muttered under his breath|低声嘟囔|phrase]]" in ANNOTATION_EXAMPLES
    assert "[[wand|" not in ANNOTATION_EXAMPLES
    assert "duplicates the source expression" in ANNOTATION_EXAMPLES


def test_english_novel_profile_validates_markers_and_source_reconstruction():
    profile = EnglishNovelProfile()

    assert profile.validate_annotated_text(
        source_text="a wand on the table",
        annotated_text="a [[wand|魔杖|noun]] on the table",
    ) is None

    malformed = profile.validate_annotated_text(
        source_text="a wand on the table",
        annotated_text="a [[wand|魔杖|noun] on the table",
    )
    invalid_pos = profile.validate_annotated_text(
        source_text="a wand on the table",
        annotated_text="a [[wand|魔杖|object]] on the table",
    )
    source_mismatch = profile.validate_annotated_text(
        source_text="a wand on the table",
        annotated_text="the [[wand|魔杖|noun]] on the table",
    )

    assert malformed is not None and malformed.code == "malformed_marker"
    assert invalid_pos is not None and invalid_pos.code == "invalid_pos"
    assert source_mismatch is not None and source_mismatch.code == "source_mismatch"


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


def test_classical_chinese_profile_validates_its_own_labels():
    profile = ClassicalChineseProfile()

    assert profile.validate_annotated_text(
        source_text="学而时习之，不亦说乎？",
        annotated_text="[[学而时习之|学习后按时复习它|特殊句式]]，不亦[[说|同悦|通假字]]乎？",
    ) is None


def test_classical_chinese_profile_builds_classical_prompt_context():
    profile = ClassicalChineseProfile()

    context = profile.build_annotator_base_context(mastered_words=["说"])
    user_prompt = context.render_role("user")

    assert "<density_profile" not in user_prompt
    assert "<selection_policy>" in profile.base_annotator_system_prompt
    assert "<mastered_words>\n[\"说\"]\n</mastered_words>" in user_prompt
    assert "文言文" in profile.base_annotator_system_prompt
    assert "[[原文字词或短语|现代汉语释义|pos]]" in profile.base_annotator_system_prompt
