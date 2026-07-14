import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from superhp_agent.corpus import CorpusStore
from superhp_agent.main import app
from superhp_agent.memory import ReadingMemoryStore
from superhp_agent.profiles import create_default_registry
from superhp_agent.runtime import (
    ReadingCardBuilder,
    ReadingFlowRouter,
    ReadingStateReader,
)
from superhp_agent.runtime.actions import (
    GENERATE_ANNOTATION,
    MARK_CHAPTER_READ,
    OPEN_CHAPTER,
    READ_ORIGINAL,
)
from superhp_agent.schemas import AgentAction
from superhp_agent.transport.reading_ws import ReadingSocketSession


class FakeWebSocket:
    def __init__(self):
        self.events = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.events.append(payload)


def write_unit(root: Path):
    path = root / "hp01" / "ch01" / "01.md"
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
summary: "Summary"
profile_id: classical_chinese
---

学而时习之，不亦说乎？
""",
        encoding="utf-8",
    )


def build_session(tmp_path, *, with_memory=False, with_classical=False):
    write_unit(tmp_path)
    if with_classical:
        write_classical_unit(tmp_path)
    corpus = CorpusStore(tmp_path)
    memory = None
    if with_memory:
        memory = ReadingMemoryStore(tmp_path / "memory" / "reading_memory.json", tmp_path / "memory" / "events.jsonl")
    state_reader = ReadingStateReader(corpus, tmp_path / "annotated", memory)
    router = ReadingFlowRouter(
        state_reader,
        card_builder=ReadingCardBuilder(profile_registry=create_default_registry()),
    )
    websocket = FakeWebSocket()
    return (
        ReadingSocketSession(
            websocket=websocket,
            flow_router=router,
            corpus=corpus,
            event_log_store=memory,
            progress_repository=memory,
            profile_registry=create_default_registry(),
        ),
        websocket,
        memory,
    )


def test_socket_hello_sends_ready_and_cards(tmp_path):
    async def run_case():
        session, websocket, _ = build_session(tmp_path)

        await session.handle_raw_message({"type": "hello", "request_id": "r1"})

        assert websocket.events[0]["type"] == "ready"
        assert websocket.events[1]["type"] == "cards.updated"
        assert websocket.events[1]["cards"][0]["actions"][0]["id"] == GENERATE_ANNOTATION
        assert websocket.events[1]["cards"][0]["actions"][0]["payload"]["unit_id"] == "hp01-ch01"

    asyncio.run(run_case())


def test_socket_hello_can_select_profile_cards(tmp_path):
    async def run_case():
        session, websocket, _ = build_session(tmp_path, with_classical=True)

        await session.handle_raw_message(
            {"type": "hello", "request_id": "r-profile", "profile_id": "classical_chinese"}
        )

        assert websocket.events[1]["type"] == "cards.updated"
        assert websocket.events[1]["profile_id"] == "classical_chinese"
        assert websocket.events[1]["current_unit_id"] == "cc-lunyu-xueer-01"
        assert websocket.events[1]["cards"][0]["title"] == "准备研读"
        assert websocket.events[1]["cards"][0]["actions"][0]["label"] == "生成注释"

    asyncio.run(run_case())


def test_socket_hello_rejects_unknown_profile(tmp_path):
    async def run_case():
        session, websocket, _ = build_session(tmp_path)

        await session.handle_raw_message(
            {"type": "hello", "request_id": "r-profile", "profile_id": "missing"}
        )

        assert websocket.events == [
            {
                "type": "error",
                "request_id": "r-profile",
                "error": {
                    "code": "unknown_profile",
                    "message": "Unknown profile id: missing",
                },
            }
        ]
        assert session.current_profile_id is None

    asyncio.run(run_case())


def test_socket_open_unit_sends_loading_opened_and_cards(tmp_path):
    async def run_case():
        session, websocket, _ = build_session(tmp_path)

        await session.handle_raw_message(
            {
                "type": "action",
                "request_id": "r2",
                "action": {
                    "id": OPEN_CHAPTER,
                    "label": "打开这一章",
                    "payload": {"unit_id": "hp01-ch01"},
                },
            }
        )

        assert [event["type"] for event in websocket.events] == [
            "chapter.loading",
            "chapter.opened",
            "cards.updated",
        ]
        assert websocket.events[0]["unit_id"] == "hp01-ch01"
        assert websocket.events[1]["chapter"]["body"] == "Body text."
        assert websocket.events[1]["chapter"]["meta"]["chapter_id"] == "hp01-ch01"
        assert websocket.events[2]["current_unit_id"] == "hp01-ch01"

    asyncio.run(run_case())


def test_socket_open_unit_updates_memory(tmp_path):
    async def run_case():
        session, _, memory = build_session(tmp_path, with_memory=True)

        await session.handle_raw_message(
            {
                "type": "action",
                "request_id": "r2",
                "action": {
                    "id": OPEN_CHAPTER,
                    "label": "打开这一章",
                    "payload": {"unit_id": "hp01-ch01"},
                },
            }
        )

        stored = memory.load()
        assert stored.current_unit_id == "hp01-ch01"
        assert stored.opened_unit_ids == ["hp01-ch01"]

    asyncio.run(run_case())


def test_socket_mark_read_updates_memory_and_cards(tmp_path):
    async def run_case():
        session, websocket, memory = build_session(tmp_path, with_memory=True)

        await session.handle_raw_message(
            {
                "type": "action",
                "request_id": "r4",
                "action": {
                    "id": MARK_CHAPTER_READ,
                    "label": "标记已读",
                    "payload": {"unit_id": "hp01-ch01"},
                },
            }
        )

        stored = memory.load()
        assert stored.read_unit_ids == ["hp01-ch01"]
        assert websocket.events[0]["type"] == "unit.marked_read"
        assert websocket.events[1]["type"] == "cards.updated"
        assert websocket.events[1]["cards"][0]["type"] == "reading"

    asyncio.run(run_case())


def test_socket_cards_message_can_request_complete_phase(tmp_path):
    async def run_case():
        session, websocket, _ = build_session(tmp_path)

        await session.handle_raw_message(
            {
                "type": "cards",
                "request_id": "r-cards",
                "current_unit_id": "hp01-ch01",
                "phase": "complete",
            }
        )

        assert websocket.events[0]["type"] == "cards.updated"
        assert websocket.events[0]["phase"] == "complete"
        assert websocket.events[0]["cards"][0]["type"] == "progress"
        assert websocket.events[0]["cards"][0]["actions"][-1]["id"] == READ_ORIGINAL

    asyncio.run(run_case())


def test_socket_invalid_action_returns_error(tmp_path):
    async def run_case():
        session, websocket, _ = build_session(tmp_path)

        await session.handle_raw_message(
            {
                "type": "action",
                "request_id": "r3",
                "action": {"id": "unknown", "label": "Unknown", "payload": {}},
            }
        )

        assert websocket.events[0]["type"] == "error"
        assert websocket.events[0]["error"]["code"] == "unsupported_action"

    asyncio.run(run_case())


def test_socket_unknown_exception_returns_internal_error(tmp_path):
    class BrokenDispatcher:
        async def dispatch(self, action: AgentAction, context, *, request_id=None):
            raise RuntimeError("boom")

    async def run_case():
        session, websocket, _ = build_session(tmp_path)
        session.action_dispatcher = BrokenDispatcher()

        await session.handle_raw_message(
            {
                "type": "action",
                "request_id": "r5",
                "action": {
                    "id": OPEN_CHAPTER,
                    "label": "打开这一章",
                    "payload": {"unit_id": "hp01-ch01"},
                },
            }
        )

        assert websocket.events[0]["type"] == "error"
        assert websocket.events[0]["error"]["code"] == "internal_error"

    asyncio.run(run_case())


def test_app_exposes_reading_websocket():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/reading") as websocket:
            ready = websocket.receive_json()
            cards = websocket.receive_json()

    assert ready["type"] == "ready"
    assert cards["type"] == "cards.updated"
