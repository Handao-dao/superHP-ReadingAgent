from superhp_agent.profiles import EnglishNovelProfile, create_default_registry


def test_default_profile_registry_returns_english_novel():
    registry = create_default_registry()

    profile = registry.get()

    assert profile.id == "english_novel"
    assert profile.renderer_hint == "english_novel"
    assert registry.get("missing").id == "english_novel"


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

