from superhp_agent.profiles import ClassicalChineseProfile, create_default_registry
from superhp_agent.runtime import (
    ReadingCardBuilder,
    ReadingFlowRouter,
    ReadingUnitState,
)
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    OPEN_ANNOTATED_COPY,
    READ_ORIGINAL,
    REVIEW_CHAPTER_VOCAB,
    START_NEXT_CHAPTER,
)


class StubStateReader:
    def __init__(self, states, current_unit_id=None):
        self.states = list(states)
        self.current_unit_id = current_unit_id

    def current_state(self, *, profile_id=None):
        if not self.current_unit_id:
            return None
        return self.get_state(self.current_unit_id, profile_id=profile_id)

    def first_state(self, *, profile_id=None):
        states = self._states_for_profile(profile_id)
        return states[0] if states else None

    def get_state(self, unit_id, *, profile_id=None):
        for state in self._states_for_profile(profile_id):
            if state.id == unit_id:
                return state
        return None

    def _states_for_profile(self, profile_id):
        if not profile_id:
            return self.states
        return [state for state in self.states if state.profile_id == profile_id]


def unit_state(**overrides):
    base = dict(
        id="hp01-ch01",
        chapter_id="hp01-ch01",
        book_id="hp01",
        book_title="Harry Potter and the Philosopher's Stone",
        chapter_no=1,
        chapter_title="The Boy Who Lived",
        section_no=1,
        section_count=1,
        summary="示例摘要",
        has_annotated_copy=False,
        is_read=False,
        vocab_count=0,
        next_unit_id="hp01-ch02",
    )
    base.update(overrides)
    return ReadingUnitState(**base)


def action_ids(card):
    return [item.id for item in card.actions]


def test_router_returns_empty_corpus_card():
    router = ReadingFlowRouter(StubStateReader([]))

    cards = router.inspect()

    assert cards[0].id == "empty-corpus"
    assert cards[0].actions == []


def test_router_starts_with_first_unit_when_no_current_unit():
    router = ReadingFlowRouter(StubStateReader([unit_state()]))

    cards = router.inspect()

    assert cards[0].id == "unit-hp01-ch01-start"
    assert "Chapter 1" in cards[0].body
    assert action_ids(cards[0]) == [GENERATE_ANNOTATION, READ_ORIGINAL]
    assert cards[0].actions[0].payload["chapter_id"] == "hp01-ch01"
    assert cards[0].actions[0].payload["unit_id"] == "hp01-ch01"


def test_router_uses_memory_current_unit_when_no_explicit_unit():
    router = ReadingFlowRouter(
        StubStateReader(
            [
                unit_state(id="hp01-ch01", chapter_no=1),
                unit_state(id="hp01-ch02", chapter_no=2),
            ],
            current_unit_id="hp01-ch02",
        )
    )

    cards = router.inspect()

    assert "Chapter 2" in cards[0].body
    assert cards[0].actions[0].payload["unit_id"] == "hp01-ch02"


def test_explicit_unit_overrides_memory_current_unit():
    router = ReadingFlowRouter(
        StubStateReader(
            [
                unit_state(id="hp01-ch01", chapter_no=1),
                unit_state(id="hp01-ch02", chapter_no=2),
            ],
            current_unit_id="hp01-ch02",
        )
    )

    cards = router.inspect(current_unit_id="hp01-ch01")

    assert "Chapter 1" in cards[0].body
    assert cards[0].actions[0].payload["unit_id"] == "hp01-ch01"


def test_unannotated_unit_offers_annotation_or_original():
    builder = ReadingCardBuilder()

    cards = builder.unit_cards(unit_state(has_annotated_copy=False))

    assert cards[0].type == "reading"
    assert action_ids(cards[0]) == [GENERATE_ANNOTATION, READ_ORIGINAL]


def test_annotated_start_unit_offers_annotation_original_and_review():
    builder = ReadingCardBuilder()

    cards = builder.unit_cards(unit_state(has_annotated_copy=True, is_read=False, vocab_count=3))

    assert cards[0].type == "reading"
    assert action_ids(cards[0]) == [
        OPEN_ANNOTATED_COPY,
        READ_ORIGINAL,
        REVIEW_CHAPTER_VOCAB,
    ]


def test_complete_unit_offers_next_review_and_reopen():
    builder = ReadingCardBuilder()

    cards = builder.complete_unit(unit_state(has_annotated_copy=True, is_read=False, vocab_count=2))

    assert cards[0].type == "progress"
    assert action_ids(cards[0]) == [
        START_NEXT_CHAPTER,
        REVIEW_CHAPTER_VOCAB,
        OPEN_ANNOTATED_COPY,
    ]
    assert cards[0].actions[0].payload["chapter_id"] == "hp01-ch02"
    assert cards[0].actions[0].payload["unit_id"] == "hp01-ch02"
    assert cards[0].actions[0].payload["completed_unit_id"] == "hp01-ch01"


def test_router_complete_phase_uses_complete_card():
    router = ReadingFlowRouter(StubStateReader([unit_state(has_annotated_copy=True, vocab_count=1)]))

    cards = router.inspect(current_unit_id="hp01-ch01", phase="complete")

    assert cards[0].id == "unit-hp01-ch01-complete"
    assert action_ids(cards[0]) == [START_NEXT_CHAPTER, REVIEW_CHAPTER_VOCAB, OPEN_ANNOTATED_COPY]


def test_classical_chinese_card_copy_uses_study_wording():
    builder = ReadingCardBuilder(ClassicalChineseProfile().card_copy)

    cards = builder.unit_cards(
        unit_state(
            book_title="论语",
            chapter_no=1,
            chapter_title="学而",
            has_annotated_copy=True,
            vocab_count=2,
        )
    )
    complete_cards = builder.complete_unit(unit_state(vocab_count=2, has_annotated_copy=True))

    assert cards[0].title == "准备研读"
    assert cards[0].body == "下一篇：《论语》第 1 篇，学而。"
    assert [action.label for action in cards[0].actions] == ["读注释本", "读原文", "复习重点"]
    assert complete_cards[0].title == "本篇完成"
    assert "文言知识点" in complete_cards[0].body
    assert complete_cards[0].actions[-1].label == "回到注释文本"


def test_card_builder_uses_unit_profile_copy_from_registry():
    builder = ReadingCardBuilder(profile_registry=create_default_registry())

    cards = builder.unit_cards(
        unit_state(
            book_title="论语",
            chapter_no=1,
            chapter_title="学而",
            profile_id="classical_chinese",
        )
    )

    assert cards[0].title == "准备研读"
    assert cards[0].body == "下一篇：《论语》第 1 篇，学而。"
    assert [action.label for action in cards[0].actions] == ["生成注释", "读原文"]


def test_router_can_start_with_first_unit_for_selected_profile():
    router = ReadingFlowRouter(
        StubStateReader(
            [
                unit_state(id="hp01-ch01", profile_id="english_novel"),
                unit_state(
                    id="cc-lunyu-xueer-01",
                    book_id="cc-lunyu",
                    book_title="论语",
                    chapter_no=1,
                    chapter_title="学而",
                    profile_id="classical_chinese",
                ),
            ]
        ),
        card_builder=ReadingCardBuilder(profile_registry=create_default_registry()),
    )

    cards = router.inspect(profile_id="classical_chinese")

    assert cards[0].id == "unit-cc-lunyu-xueer-01-start"
    assert cards[0].title == "准备研读"


def test_router_empty_corpus_uses_selected_profile_copy():
    router = ReadingFlowRouter(
        StubStateReader([]),
        card_builder=ReadingCardBuilder(profile_registry=create_default_registry()),
    )

    cards = router.inspect(profile_id="classical_chinese")

    assert cards[0].id == "empty-corpus"
    assert cards[0].title == "暂无研读文本"
