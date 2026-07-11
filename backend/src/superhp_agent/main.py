"""FastAPI entrypoint and application composition root.

This module wires the long-lived services together. HTTP endpoints expose read
models for the frontend, while the WebSocket endpoint delegates guided reading
side effects to ``ReadingSocketSession`` and the runtime action dispatcher.
"""

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from superhp_agent.application import build_container
from superhp_agent.contracts import AgentCard, ReadingUnitDetail, ReadingUnitMeta
from superhp_agent.corpus import (
    CorpusError,
    ReadingUnit,
    ReadingUnitDocument,
)
from superhp_agent.domain.vocabulary import normalize_pos
from superhp_agent.schemas import (
    AddBookmarkRequest,
    AddVocabularyRequest,
    AddVocabularyResponse,
    BookmarkEntry,
    MarkByWordRequest,
    MutationResponse,
    ProfileMeta,
    SetMasteredRequest,
    VocabularyEntry,
    WordLookupRequest,
    WordLookupResult,
)
from superhp_agent.transport.reading_ws import ReadingSocketSession

# These singletons are intentionally created at import time: they are cheap,
# stateless or locally stateful, and FastAPI can reuse them across requests.
container = build_container()
# Compatibility aliases keep existing route code and tests stable while HTTP
# routers are moved to dependency-injected modules in later steps.
settings = container.settings
profile_registry = container.profile_registry
default_profile = container.default_profile
corpus = container.corpus
event_log_store = container.event_log_store
reading_progress_repository = container.reading_progress_repository
db = container.db
vocabulary_repository = container.vocabulary_repository
bookmark_repository = container.bookmark_repository
annotated_copies = container.annotated_copies
annotator_service = container.annotator_service
lookup_service = container.lookup_service
state_reader = container.state_reader
flow_router = container.flow_router

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
    progress = reading_progress_repository.load()
    is_read = unit.id in set(progress.read_unit_ids)
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
        has_annotated_copy=annotated_copies.exists_any(unit.id),
        status="read" if is_read else "unread",
        vocab_count=vocabulary_repository.count_vocabulary_for_unit(unit.id),
        profile_id=unit.profile_id,
        language_id=unit.language_id,
    )


def _unit_detail(doc: ReadingUnitDocument) -> ReadingUnitDetail:
    return ReadingUnitDetail(meta=_unit_meta(doc.meta), body=doc.body, body_kind="source")


def _vocabulary_entry(row: dict) -> VocabularyEntry:
    """Normalize SQLite rows before they cross the API boundary."""
    return VocabularyEntry(
        id=int(row["id"]),
        book_id=str(row["book_id"]),
        profile_id=str(row["profile_id"]),
        language_id=str(row["language_id"]),
        word=str(row["word"]),
        translation=str(row["translation"]),
        global_translation=str(row["global_translation"]),
        pos=str(row.get("pos") or "other"),
        mastered=bool(row["mastered"]),
        context=str(row["context"] or ""),
        encounter_count=int(row["encounter_count"]),
        unit_id=str(row["unit_id"]),
        chapter_id=str(row["chapter_id"]),
        first_seen_at=str(row["first_seen_at"] or ""),
        last_seen_at=str(row["last_seen_at"] or ""),
    )


def _bookmark_entry(row: dict) -> BookmarkEntry:
    """Normalize bookmark rows before returning them to the frontend."""
    return BookmarkEntry(
        id=int(row["id"]),
        unit_id=str(row["unit_id"]),
        chapter_id=str(row["chapter_id"]),
        body_kind=str(row["body_kind"]),
        page_index=int(row["page_index"]),
        progress_ratio=float(row["progress_ratio"]),
        total_pages=int(row["total_pages"]),
        label=str(row["label"] or ""),
        excerpt=str(row["excerpt"] or ""),
        paragraph_index=int(row["paragraph_index"]),
        created_at=str(row["created_at"] or ""),
    )


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/profiles", response_model=list[ProfileMeta])
async def list_profiles():
    return [
        ProfileMeta(
            id=profile.id,
            language_id=profile.language_id,
            label=profile.label,
            renderer_hint=profile.renderer_hint,
            is_default=profile.id == profile_registry.default_profile_id,
        )
        for profile in profile_registry.list_profiles()
    ]


@app.get("/api/units", response_model=list[ReadingUnitMeta])
async def list_units(profile_id: str | None = None):
    return [
        _unit_meta(item)
        for item in corpus.list_units()
        if not profile_id or item.profile_id == profile_id
    ]


@app.get("/api/units/{unit_id}", response_model=ReadingUnitDetail)
async def get_unit(unit_id: str):
    try:
        doc = corpus.get_unit(unit_id)
    except CorpusError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _unit_detail(doc)


# Compatibility endpoints keep older frontend/tests working while the domain
# language moves from whole chapters to finer reading units.
@app.get("/api/chapters", response_model=list[ReadingUnitMeta])
async def list_chapters():
    return await list_units()


@app.get("/api/chapters/{chapter_id}", response_model=ReadingUnitDetail)
async def get_chapter(chapter_id: str):
    return await get_unit(chapter_id)


@app.get("/api/vocabulary", response_model=list[VocabularyEntry])
async def list_vocabulary(
    unit_id: str | None = Query(default=None),
    chapter_id: str | None = Query(default=None),
    profile_id: str | None = Query(default=None),
    book_id: str | None = Query(default=None),
):
    return [
        _vocabulary_entry(row)
        for row in vocabulary_repository.list_vocabulary(
            unit_id=unit_id,
            chapter_id=chapter_id,
            profile_id=profile_id,
            book_id=book_id,
        )
    ]


@app.get("/api/bookmarks", response_model=list[BookmarkEntry])
async def list_bookmarks(unit_id: str | None = Query(default=None)):
    return [_bookmark_entry(row) for row in bookmark_repository.list_bookmarks(unit_id=unit_id)]


@app.post("/api/bookmarks", response_model=BookmarkEntry)
async def add_bookmark(payload: AddBookmarkRequest):
    if payload.body_kind not in {"source", "annotated"}:
        raise HTTPException(status_code=400, detail="body_kind must be source or annotated")
    try:
        unit = corpus.get_unit(payload.unit_id).meta
        bookmark_id = bookmark_repository.add_bookmark(
            unit,
            body_kind=payload.body_kind,
            page_index=payload.page_index,
            progress_ratio=payload.progress_ratio,
            total_pages=payload.total_pages,
            label=payload.label,
            excerpt=payload.excerpt,
            paragraph_index=payload.paragraph_index,
        )
    except CorpusError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = bookmark_repository.list_bookmarks(unit_id=unit.id)
    for row in rows:
        if int(row["id"]) == bookmark_id:
            return _bookmark_entry(row)
    raise HTTPException(status_code=500, detail="bookmark was not saved")


@app.delete("/api/bookmarks/{bookmark_id}", response_model=MutationResponse)
async def delete_bookmark(bookmark_id: int):
    if not bookmark_repository.delete_bookmark(bookmark_id):
        raise HTTPException(status_code=404, detail="bookmark not found")
    return MutationResponse(ok=True)


@app.post("/api/word-lookup", response_model=WordLookupResult)
async def lookup_word(payload: WordLookupRequest):
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="word is required")
    try:
        return await lookup_service.lookup(word, payload.sentence.strip(), profile_id=payload.profile_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/vocabulary", response_model=AddVocabularyResponse)
async def add_vocabulary(payload: AddVocabularyRequest):
    try:
        unit = corpus.get_unit(payload.unit_id).meta
        vocab_id = vocabulary_repository.add_manual_vocabulary(
            unit,
            word=payload.word,
            translation=payload.translation,
            context=payload.context,
            pos=payload.pos,
        )
    except CorpusError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AddVocabularyResponse(
        id=vocab_id,
        book_id=unit.book_id,
        profile_id=unit.profile_id,
        language_id=unit.language_id,
        word=payload.word.strip(),
        translation=payload.translation.strip(),
        pos=normalize_pos(payload.pos),
        unit_id=unit.id,
    )


@app.patch("/api/vocabulary/{vocab_id}/master", response_model=MutationResponse)
async def set_vocabulary_mastered(vocab_id: int, payload: SetMasteredRequest):
    if not vocabulary_repository.set_mastered(vocab_id, payload.mastered):
        raise HTTPException(status_code=404, detail="vocabulary item not found")
    return MutationResponse(ok=True)


@app.delete("/api/vocabulary/{vocab_id}", response_model=MutationResponse)
async def delete_vocabulary(vocab_id: int):
    if not vocabulary_repository.delete_vocabulary(vocab_id):
        raise HTTPException(status_code=404, detail="vocabulary item not found")
    return MutationResponse(ok=True)


@app.post("/api/vocabulary/mark-by-word", response_model=MutationResponse)
async def mark_vocabulary_by_word(payload: MarkByWordRequest):
    vocabulary_repository.set_mastered_by_word(
        payload.word,
        payload.mastered,
        language_id=profile_registry.get(payload.profile_id).language_id,
    )
    return MutationResponse(ok=True)


@app.get("/api/agent-cards", response_model=list[AgentCard])
async def get_agent_cards(
    current_chapter_id: str | None = Query(default=None),
    current_unit_id: str | None = Query(default=None),
    profile_id: str | None = None,
    phase: str = Query(default="start"),
):
    return flow_router.inspect(
        current_chapter_id=current_chapter_id,
        current_unit_id=current_unit_id,
        profile_id=profile_id,
        phase=phase,
    )


@app.websocket("/ws/reading")
async def reading_socket(websocket: WebSocket):
    session = ReadingSocketSession(
        websocket=websocket,
        flow_router=flow_router,
        corpus=corpus,
        event_log_store=event_log_store,
        progress_repository=reading_progress_repository,
        annotated_copies=annotated_copies,
        annotator_service=annotator_service,
        db=vocabulary_repository,
    )
    try:
        await session.run()
    except WebSocketDisconnect:
        event_log_store.log_event("session_disconnected")
        return
