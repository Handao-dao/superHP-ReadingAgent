import asyncio
from pathlib import Path

import pytest

from superhp_agent.corpus import CorpusStore
from superhp_agent.memory import ReadingMemoryStore
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
from superhp_agent.schemas import AgentAction
from superhp_agent.services.annotator import AnnotationResult, VocabItem
from superhp_agent.storage import AppDB


class FakeAnnotator:
    async def annotate_text(
        self,
        text,
        *,
        mastered_words=None,
        level="intermediate",
        event_sink=None,
        request_id=None,
    ):
        return AnnotationResult(
            annotated_text="Body [[text|文本]].",
            vocabulary=[VocabItem(word="text", translation="文本", context="Body text.")],
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


def memory_store(tmp_path):
    return ReadingMemoryStore(tmp_path / "memory" / "reading_memory.json", tmp_path / "memory" / "events.jsonl")


def test_dispatch_open_unit_emits_events_and_updates_context(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)
        events = []

        async def emit(event_type, **payload):
            events.append({"type": event_type, **payload})

        memory = memory_store(tmp_path)
        context = ActionContext(corpus=CorpusStore(corpus_root), emit=emit, memory_store=memory)
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
        events = []

        async def emit(event_type, **payload):
            events.append({"type": event_type, **payload})

        memory = memory_store(tmp_path)
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            emit=emit,
            memory_store=memory,
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
        events = []

        async def emit(event_type, **payload):
            events.append({"type": event_type, **payload})

        memory = memory_store(tmp_path)
        context = ActionContext(corpus=CorpusStore(corpus_root), emit=emit, memory_store=memory)
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
        events = []

        async def emit(event_type, **payload):
            events.append({"type": event_type, **payload})

        memory = memory_store(tmp_path)
        annotated_dir = tmp_path / "data" / "annotated"
        db = AppDB(tmp_path / "app.sqlite3")
        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            emit=emit,
            memory_store=memory,
            annotated_dir=annotated_dir,
            annotator_service=FakeAnnotator(),
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
        assert (annotated_dir / "hp01-ch01.annotated.md").exists()
        assert "Body [[text|文本]]." in (annotated_dir / "hp01-ch01.annotated.md").read_text(encoding="utf-8")
        assert memory.load().annotated_unit_ids == ["hp01-ch01"]
        assert db.count_vocabulary_for_unit("hp01-ch01") == 1
        assert db.list_vocabulary(unit_id="hp01-ch01")[0]["word"] == "text"

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
        events = []

        async def emit(event_type, **payload):
            events.append({"type": event_type, **payload})

        context = ActionContext(
            corpus=CorpusStore(corpus_root),
            emit=emit,
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


def test_dispatch_unknown_action_raises(tmp_path):
    async def run_case():
        corpus_root = tmp_path / "corpus"
        write_unit(corpus_root)

        async def emit(event_type, **payload):
            return None

        context = ActionContext(corpus=CorpusStore(corpus_root), emit=emit)
        dispatcher = ActionDispatcher()

        with pytest.raises(UnsupportedActionError):
            await dispatcher.dispatch(AgentAction(id="unknown", label="Unknown", payload={}), context)

    asyncio.run(run_case())
