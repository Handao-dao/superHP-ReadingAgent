"""FastAPI entrypoint and application composition root.

This module wires the long-lived services together. HTTP endpoints expose read
models for the frontend, while the WebSocket endpoint delegates guided reading
side effects to ``ReadingSocketSession`` and the runtime action dispatcher.
"""

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from superhp_agent.config import get_settings
from superhp_agent.corpus import (
    CorpusError,
    CorpusStore,
    ReadingUnit,
    ReadingUnitDocument,
)
from superhp_agent.memory import ReadingMemoryStore
from superhp_agent.providers.factory import make_provider
from superhp_agent.runtime import ReadingFlowRouter, ReadingStateReader
from superhp_agent.schemas import (
    AgentCard,
    ChapterDetail,
    ChapterMeta,
    ReadingUnitDetail,
    ReadingUnitMeta,
    VocabularyEntry,
)
from superhp_agent.services.annotator import LazyAnnotatorService
from superhp_agent.storage import AppDB
from superhp_agent.transport.reading_ws import ReadingSocketSession

# These singletons are intentionally created at import time: they are cheap,
# stateless or locally stateful, and FastAPI can reuse them across requests.
settings = get_settings()
corpus = CorpusStore(settings.corpus_dir)
memory_store = ReadingMemoryStore(settings.reading_memory_path, settings.event_log_path)
db = AppDB(settings.db_path)
# LLM providers are lazy so the app can boot and serve corpus/memory endpoints
# even when no API key has been configured yet.
annotator_service = LazyAnnotatorService(
    lambda: make_provider(settings),
    max_chunk_words=settings.annotation_max_chunk_words,
    max_concurrency=settings.annotation_max_concurrency,
)
state_reader = ReadingStateReader(corpus, settings.annotated_dir, memory_store, db)
flow_router = ReadingFlowRouter(state_reader)

app = FastAPI(title="SuperHP Agent Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _unit_meta(unit: ReadingUnit) -> ReadingUnitMeta:
    """Translate internal corpus metadata into the public API schema."""
    return ReadingUnitMeta(
        id=unit.id,
        chapter_id=unit.chapter_id,
        book_id=unit.book_id,
        book_title=unit.book_title,
        chapter_no=unit.chapter_no,
        chapter_title=unit.chapter_title,
        section_no=unit.section_no,
        section_count=unit.section_count,
        summary=unit.summary,
        has_annotated_copy=(settings.annotated_dir / f"{unit.id}.annotated.md").exists(),
    )


def _unit_detail(doc: ReadingUnitDocument) -> ReadingUnitDetail:
    return ReadingUnitDetail(meta=_unit_meta(doc.meta), body=doc.body, body_kind="source")


def _vocabulary_entry(row: dict) -> VocabularyEntry:
    """Normalize SQLite rows before they cross the API boundary."""
    return VocabularyEntry(
        id=int(row["id"]),
        word=str(row["word"]),
        translation=str(row["translation"]),
        global_translation=str(row["global_translation"]),
        mastered=bool(row["mastered"]),
        context=str(row["context"] or ""),
        encounter_count=int(row["encounter_count"]),
        unit_id=str(row["unit_id"]),
        chapter_id=str(row["chapter_id"]),
        first_seen_at=str(row["first_seen_at"] or ""),
        last_seen_at=str(row["last_seen_at"] or ""),
    )


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/units", response_model=list[ReadingUnitMeta])
async def list_units():
    return [_unit_meta(item) for item in corpus.list_units()]


@app.get("/api/units/{unit_id}", response_model=ReadingUnitDetail)
async def get_unit(unit_id: str):
    try:
        doc = corpus.get_unit(unit_id)
    except CorpusError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _unit_detail(doc)


# Compatibility endpoints keep older frontend/tests working while the domain
# language moves from whole chapters to finer reading units.
@app.get("/api/chapters", response_model=list[ChapterMeta])
async def list_chapters():
    return await list_units()


@app.get("/api/chapters/{chapter_id}", response_model=ChapterDetail)
async def get_chapter(chapter_id: str):
    return await get_unit(chapter_id)


@app.get("/api/vocabulary", response_model=list[VocabularyEntry])
async def list_vocabulary(
    unit_id: str | None = Query(default=None),
    chapter_id: str | None = Query(default=None),
):
    return [_vocabulary_entry(row) for row in db.list_vocabulary(unit_id=unit_id, chapter_id=chapter_id)]


@app.get("/api/agent-cards", response_model=list[AgentCard])
async def get_agent_cards(
    current_chapter_id: str | None = Query(default=None),
    current_unit_id: str | None = Query(default=None),
    phase: str = Query(default="start"),
):
    return flow_router.inspect(current_chapter_id=current_chapter_id, current_unit_id=current_unit_id, phase=phase)


@app.websocket("/ws/reading")
async def reading_socket(websocket: WebSocket):
    session = ReadingSocketSession(
        websocket=websocket,
        flow_router=flow_router,
        corpus=corpus,
        memory_store=memory_store,
        annotated_dir=settings.annotated_dir,
        annotator_service=annotator_service,
        db=db,
    )
    try:
        await session.run()
    except WebSocketDisconnect:
        memory_store.log_event("session_disconnected")
        return
