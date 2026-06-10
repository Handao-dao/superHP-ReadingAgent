from superhp_agent.runtime import (
    ReadingCardBuilder,
    ReadingFlowRouter,
    ReadingUnitState,
)
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    MARK_CHAPTER_READ,
    OPEN_ANNOTATED_COPY,
    OPEN_CHAPTER,
    READ_ORIGINAL,
    REVIEW_CHAPTER_VOCAB,
    START_NEXT_CHAPTER,
)


class StubStateReader:
    def __init__(self, states, current_unit_id=None):
        self.states = list(states)
        self.current_unit_id = current_unit_id

    def current_state(self):
        if not self.current_unit_id:
            return None
        return self.get_state(self.current_unit_id)

    def first_state(self):
        return self.states[0] if self.states else None

    def get_state(self, unit_id):
        for state in self.states:
            if state.id == unit_id:
                return state
        return None


def unit_state(**overrides):
    base = dict(
        id="hp01-ch01-sec01",
        chapter_id="hp01-ch01",
        book_id="hp01",
        book_title="Harry Potter and the Philosopher's Stone",
        chapter_no=1,
        chapter_title="The Boy Who Lived",
        section_no=1,
        section_count=2,
        summary="示例摘要",
        has_annotated_copy=False,
        is_read=False,
        vocab_count=0,
        next_unit_id="hp01-ch01-sec02",
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

    assert cards[0].id == "start-reading"
    assert "第 1/2 节" in cards[0].body
    assert action_ids(cards[0]) == [OPEN_CHAPTER]
    assert cards[0].actions[0].payload["chapter_id"] == "hp01-ch01-sec01"
    assert cards[0].actions[0].payload["unit_id"] == "hp01-ch01-sec01"


def test_router_uses_memory_current_unit_when_no_explicit_unit():
    router = ReadingFlowRouter(
        StubStateReader(
            [
                unit_state(id="hp01-ch01-sec01", section_no=1),
                unit_state(id="hp01-ch01-sec02", section_no=2),
            ],
            current_unit_id="hp01-ch01-sec02",
        )
    )

    cards = router.inspect()

    assert "第 2/2 节" in cards[0].body
    assert cards[0].actions[0].payload["unit_id"] == "hp01-ch01-sec02"


def test_explicit_unit_overrides_memory_current_unit():
    router = ReadingFlowRouter(
        StubStateReader(
            [
                unit_state(id="hp01-ch01-sec01", section_no=1),
                unit_state(id="hp01-ch01-sec02", section_no=2),
            ],
            current_unit_id="hp01-ch01-sec02",
        )
    )

    cards = router.inspect(current_unit_id="hp01-ch01-sec01")

    assert "第 1/2 节" in cards[0].body
    assert cards[0].actions[0].payload["unit_id"] == "hp01-ch01-sec01"


def test_unannotated_unit_offers_annotation_or_original():
    builder = ReadingCardBuilder()

    cards = builder.unit_cards(unit_state(has_annotated_copy=False))

    assert cards[0].type == "annotation"
    assert action_ids(cards[0]) == [GENERATE_ANNOTATION, READ_ORIGINAL]


def test_annotated_unread_unit_offers_continue_review_and_mark_read():
    builder = ReadingCardBuilder()

    cards = builder.unit_cards(unit_state(has_annotated_copy=True, is_read=False, vocab_count=3))

    assert cards[0].type == "reading"
    assert action_ids(cards[0]) == [
        OPEN_ANNOTATED_COPY,
        REVIEW_CHAPTER_VOCAB,
        MARK_CHAPTER_READ,
    ]


def test_read_unit_offers_review_next_and_reopen():
    builder = ReadingCardBuilder()

    cards = builder.unit_cards(unit_state(has_annotated_copy=True, is_read=True, vocab_count=2))

    assert cards[0].type == "progress"
    assert action_ids(cards[0]) == [
        REVIEW_CHAPTER_VOCAB,
        START_NEXT_CHAPTER,
        OPEN_ANNOTATED_COPY,
    ]
    assert cards[0].actions[1].payload["chapter_id"] == "hp01-ch01-sec02"
    assert cards[0].actions[1].payload["unit_id"] == "hp01-ch01-sec02"