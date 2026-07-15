import asyncio
from pathlib import Path

import pytest

from superhp_agent.contracts import AgentAction
from superhp_agent.contracts.annotation import (
    AnnotationItem,
    AnnotationResult,
    ServiceIssue,
)
from superhp_agent.corpus import CorpusStore
from superhp_agent.runtime.action_dispatcher import (
    ActionContext,
    ActionDispatcher,
    UnsupportedActionError,
)
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    MARK_CHAPTER_READ,
    OPEN_ANNOTATED_COPY,
    OPEN_CHAPTER,
    START_NEXT_CHAPTER,
)
from superhp_agent.storage import AppDB
from tests.fakes import InMemoryReadingState, RecordingEventSink


class FakeAnnotator:
    def __init__(self):
        self.mastered_words = []
        self.profile_ids = []
        self.selection_policy_ids = []

    async def annotate_text(
        self,
        text,
        *,
        mastered_words=None,
        event_sink=None,
        request_id=None,
        profile_id=None,
        selection_policy_id=None,
    ):
        self.mastered_words.append(mastered_words or [])
        self.profile_ids.append(profile_id)
        self.selection_policy_ids.append(selection_policy_id)
        return AnnotationResult(
            annotated_text="Body [[text|文本]].",
            vocabulary=[AnnotationItem(word="text", translation="文本", context="Body text.")],
            validated_chunk_count=1,
            total_chunk_count=1,
        )


class FullyDegradedAnnotator:
    async def annotate_text(self, text, **kwargs):
        return AnnotationResult(
            annotated_text=text,
            vocabulary=[],
            issues=[
                ServiceIssue(
                    category="provider",
                    code="provider_failed",
                    message="The model request failed.",
                    chunk_index=1,
                )
            ],
            validated_chunk_count=0,
            total_chunk_count=1,
        )


def write_unit(root: Path):
    path = root / "hp01" / "hp01-ch01.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
id: hp01-ch01
chapter_id: hp01-ch01
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 1
chapter_title: "The Boy Who Lived"
summary: "Summary"
---

Body text.
""",
        encoding="utf-8",
    )


def write_second_unit(root: Path):
    path = root / "hp01" / "hp01-ch02.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
id: hp01-ch02
chapter_id: hp01-ch02
book_id: hp01
book_title: "Harry Potter and the Philosopher's Stone"
chapter_no: 2
chapter_title: "The Vanishing Glass"
summary: "Summary"
---

Second body.
""",
        encoding="utf-8",
    )


def write_classical_unit(root: Path):
    path = root / "classical_chinese" / "lunyu-xueer.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """---
id: cc-lunyu-xueer-01
chapter_id: cc-lunyu-xueer-01
book_id: cc-lunyu
book_title: "论语"
chapter_no: 1
chapter_title: "学而"
summary: "孔子谈学习、复习与朋友来访之乐。"
profile_id: classical_chinese
---

学而时习之，不亦说乎？
有朋自远方来，不亦乐乎？
人不知而不愠，不亦君子乎？
""",
        encoding="utf-8",
    )


def memory_store():
    return InMemoryReadingState()


def test_dispatch_open_unit_emits_events_and_updates_context(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        sink = RecordingEventSink()
        events = sink.events

        memory = memory_store()
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            event_sink=sink,
            event_log_store=memory,
            progress_repository=memory,
        )
        dispatcher = ActionDispatcher()

        await dispatcher.dispatch(
            AgentAction(id=OPEN_CHAPTER, label="打开", payload={"unit_id": "hp01-ch01"}),
            context,
            request_id="r1",
        )

        assert [event["type"] for event in events] == ["chapter.loading", "chapter.opened"]
        assert events[1]["unit"]["body"] == "Body text."
        assert context.current_unit_id == "hp01-ch01"
        assert memory.load().opened_unit_ids == ["hp01-ch01"]

    asyncio.run(run_case())


def test_dispatch_mark_read_uses_current_unit(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        sink = RecordingEventSink()
        events = sink.events

        memory = memory_store()
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            event_sink=sink,
            event_log_store=memory,
            progress_repository=memory,
            current_unit_id="hp01-ch01",
        )
        dispatcher = ActionDispatcher()

        await dispatcher.dispatch(
            AgentAction(id=MARK_CHAPTER_READ, label="标记已读", payload={}),
            context,
            request_id="r2",
        )

        assert events[0]["type"] == "unit.marked_read"
        assert memory.load().read_unit_ids == ["hp01-ch01"]

    asyncio.run(run_case())


def test_dispatch_start_next_marks_completed_and_selects_next_unit(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        write_second_unit(corpus_root)
        sink = RecordingEventSink()
        events = sink.events

        memory = memory_store()
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            event_sink=sink,
            event_log_store=memory,
            progress_repository=memory,
        )
        dispatcher = ActionDispatcher()

        await dispatcher.dispatch(
            AgentAction(
                id=START_NEXT_CHAPTER,
                label="读下一章",
                payload={
                    "unit_id": "hp01-ch02",
                    "completed_unit_id": "hp01-ch01",
                },
            ),
            context,
            request_id="r-next",
        )

        stored = memory.load()
        assert events[0]["type"] == "unit.marked_read"
        assert events[0]["unit_id"] == "hp01-ch01"
        assert stored.read_unit_ids == ["hp01-ch01"]
        assert stored.current_unit_id == "hp01-ch02"
        assert context.current_unit_id == "hp01-ch02"

    asyncio.run(run_case())


def test_dispatch_generate_annotation_saves_copy_and_vocabulary(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        sink = RecordingEventSink()
        events = sink.events

        memory = memory_store()
        annotated_dir = tmp_path / "data" / "annotated"
        db = AppDB(tmp_path / "app.sqlite3")
        corpus = CorpusStore(corpus_root)
        unit = corpus.get_unit("hp01-ch01").meta
        mastered_id = db.add_manual_vocabulary(
            unit,
            word="Body",
            translation="正文",
            context="Body text.",
        )
        db.set_mastered(mastered_id, True)
        irrelevant_id = db.add_manual_vocabulary(
            unit,
            word="known",
            translation="已知",
            context="Known word.",
        )
        db.set_mastered(irrelevant_id, True)
        annotator = FakeAnnotator()
        context = ActionContext(
            corpus=corpus,
            event_sink=sink,
            event_log_store=memory,
            progress_repository=memory,
            annotated_dir=annotated_dir,
            annotator_service=annotator,
            db=db,
        )
        dispatcher = ActionDispatcher()

        await dispatcher.dispatch(
            AgentAction(id=GENERATE_ANNOTATION, label="生成译注", payload={"unit_id": "hp01-ch01"}),
            context,
            request_id="r3",
        )

        assert [event["type"] for event in events] == [
            "annotation.started",
            "annotation.progress",
            "annotation.completed",
            "chapter.opened",
        ]
        assert events[2]["stored_vocabulary_count"] == 1
        assert events[-1]["unit"]["body"] == "Body [[text|文本]]."
        assert events[-1]["unit"]["body_kind"] == "annotated"
        assert annotator.mastered_words == [["Body"]]
        assert annotator.profile_ids == ["english_novel"]
        annotated_file = annotated_dir / "hp01-ch01.annotated.md"
        assert annotated_file.exists()
        annotated_text = annotated_file.read_text(encoding="utf-8")
        assert "level:" not in annotated_text
        assert "Body [[text|文本]]." in annotated_text
        assert db.count_vocabulary_for_unit("hp01-ch01") == 1
        assert "text" in [row["word"] for row in db.list_vocabulary(unit_id="hp01-ch01")]

    asyncio.run(run_case())


def test_dispatch_generate_annotation_passes_unit_profile_id(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_classical_unit(corpus_root)
        annotator = FakeAnnotator()
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            annotated_dir=tmp_path / "data" / "annotated",
            annotator_service=annotator,
        )
        dispatcher = ActionDispatcher()

        await dispatcher.dispatch(
            AgentAction(id=GENERATE_ANNOTATION, label="生成注释", payload={"unit_id": "cc-lunyu-xueer-01"}),
            context,
        )

        assert annotator.profile_ids == ["classical_chinese"]
        annotated_file = tmp_path / "data" / "annotated" / "cc-lunyu-xueer-01.annotated.md"
        assert "profile_id: classical_chinese" in annotated_file.read_text(encoding="utf-8")

    asyncio.run(run_case())


def test_dispatch_generate_annotation_passes_optional_series_policy(tmp_path):
    class Resolver:
        def selection_policy_id_for_book(self, book_id, *, profile_id=None):
            assert book_id == "hp01"
            assert profile_id == "english_novel"
            return "harry_potter"

    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        annotator = FakeAnnotator()
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            annotated_dir=tmp_path / "data" / "annotated",
            annotator_service=annotator,
            selection_policy_resolver=Resolver(),
        )

        await ActionDispatcher().dispatch(
            AgentAction(
                id=GENERATE_ANNOTATION,
                label="生成注释",
                payload={"unit_id": "hp01-ch01"},
            ),
            context,
        )

        assert annotator.selection_policy_ids == ["harry_potter"]

    asyncio.run(run_case())


def test_dispatch_returns_original_without_persisting_fully_degraded_result(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        annotated_dir = tmp_path / "data" / "annotated"
        memory = InMemoryReadingState()
        sink = RecordingEventSink()
        events = sink.events

        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            event_sink=sink,
            event_log_store=memory,
            progress_repository=memory,
            annotated_dir=annotated_dir,
            annotator_service=FullyDegradedAnnotator(),
        )

        await ActionDispatcher().dispatch(
            AgentAction(
                id=GENERATE_ANNOTATION,
                label="生成译注",
                payload={"unit_id": "hp01-ch01"},
            ),
            context,
            request_id="r-degraded",
        )

        completed = next(event for event in events if event["type"] == "annotation.completed")
        opened = events[-1]
        assert completed["status"] == "degraded"
        assert completed["persisted"] is False
        assert completed["provider_error_count"] == 1
        assert opened["unit"]["body"] == "Body text."
        assert opened["unit"]["body_kind"] == "original"
        assert not annotated_dir.exists()

    asyncio.run(run_case())


def test_dispatch_open_annotated_copy_reads_saved_body(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        annotated_dir = tmp_path / "data" / "annotated"
        annotated_dir.mkdir(parents=True)
        (annotated_dir / "hp01-ch01.annotated.md").write_text(
            "---\nbody_kind: annotated\n---\n\nSaved [[body|正文]].\n",
            encoding="utf-8",
        )
        sink = RecordingEventSink()
        events = sink.events

        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            event_sink=sink,
            annotated_dir=annotated_dir,
        )
        dispatcher = ActionDispatcher()

        await dispatcher.dispatch(
            AgentAction(id=OPEN_ANNOTATED_COPY, label="回看译注", payload={"unit_id": "hp01-ch01"}),
            context,
        )

        assert [event["type"] for event in events] == ["chapter.loading", "chapter.opened"]
        assert events[-1]["unit"]["body"] == "Saved [[body|正文]]."
        assert events[-1]["unit"]["body_kind"] == "annotated"

    asyncio.run(run_case())


def test_dispatch_open_annotated_copy_generates_missing_copy(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        annotated_dir = tmp_path / "data" / "annotated"
        annotated_dir.mkdir(parents=True)
        sink = RecordingEventSink()
        events = sink.events

        annotator = FakeAnnotator()
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            event_sink=sink,
            annotated_dir=annotated_dir,
            annotator_service=annotator,
        )
        dispatcher = ActionDispatcher()

        await dispatcher.dispatch(
            AgentAction(id=OPEN_ANNOTATED_COPY, label="回看译注", payload={"unit_id": "hp01-ch01"}),
            context,
        )

        assert [event["type"] for event in events] == [
            "annotation.started",
            "annotation.progress",
            "annotation.completed",
            "chapter.opened",
        ]
        assert (annotated_dir / "hp01-ch01.annotated.md").exists()

    asyncio.run(run_case())


def test_dispatch_unknown_action_raises(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)

        context = ActionContext(corpus=CorpusStore(corpus_root))
        dispatcher = ActionDispatcher()

        with pytest.raises(UnsupportedActionError):
            await dispatcher.dispatch(AgentAction(id="unknown", label="Unknown", payload={}), context)

    asyncio.run(run_case())
