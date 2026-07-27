"""Round-trip tests for durable recommendation Agent sessions."""

from dataclasses import replace

from superhp_agent.contracts import (
    BookDifficulty,
    BookRecommendationHandoff,
    BookSnapshot,
    LLMToolCall,
    OperationalReadingBand,
    ReadingDifficultyEvidence,
    ReadingPreference,
    RecommendationAgentMessage,
    RecommendationAgentMessageRole,
    RecommendationAgentPhase,
    RecommendationAgentSession,
    RecommendationOrigin,
    RecommendationRequest,
)
from superhp_agent.ports import RecommendationSessionRepository
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import SQLiteRecommendationSessionRepository


def complex_session() -> RecommendationAgentSession:
    current_book = BookSnapshot(
        book_id="detective-1",
        title="A Difficult Mystery",
        title_zh="一本较难的侦探小说",
        author="A. Writer",
        difficulty=BookDifficulty(900, 900),
        genres=("mystery", "detective"),
        progress=0.3,
    )
    handoff = BookRecommendationHandoff(
        current_book=current_book,
        evidence=ReadingDifficultyEvidence(
            observed_word_count=7200,
            observed_chapter_count=3,
            lookup_density=12.1,
            unique_lookup_density=9.8,
            repeated_lookup_density=2.3,
            annotated_lookup_density=4.0,
            actual_annotation_density=14.0,
            annotation_target=16,
        ),
        target_band=OperationalReadingBand(
            650,
            800,
            confidence=0.7,
            evidence_source="reading_monitor",
        ),
        preserve_genre_by_default=False,
    )
    tool_call = LLMToolCall(
        id="search-1",
        name="search_local_book_catalog",
        arguments={
            "lexile_min": 650,
            "lexile_max": 800,
            "genres": ["mystery"],
        },
        raw_arguments='{"lexile_min":650,"lexile_max":800}',
    )
    return RecommendationAgentSession(
        session_id="recommendation-会话-1",
        request=RecommendationRequest(
            origin=RecommendationOrigin.DIFFICULTY_ALERT,
            preferred_genres=("mystery",),
            excluded_traits=("horror",),
            reading_preference=ReadingPreference.FLUENCY_FIRST,
            operational_band=OperationalReadingBand(
                650,
                800,
                confidence=0.6,
                evidence_source="user_history",
            ),
            reference_books=(current_book,),
            handoff=handoff,
            user_notes="希望故事节奏轻快。",
        ),
        phase=RecommendationAgentPhase.SEARCHING,
        conversation=(
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.USER,
                content="我还想读侦探故事。",
            ),
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.ASSISTANT,
                tool_calls=(tool_call,),
            ),
            RecommendationAgentMessage(
                role=RecommendationAgentMessageRole.TOOL,
                content='{"ok":true,"candidates":[]}',
                tool_call_id="search-1",
                tool_name="search_local_book_catalog",
            ),
        ),
        tool_call_count=1,
        observed_catalog_ids=("cam-jansen",),
    )


def test_sqlite_repository_round_trips_complete_session(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        repository = db.recommendation_session_repository
        session = complex_session()

        repository.save(session)

        assert repository.load(session.session_id) == session
        row = db.database.connection.execute(
            """
            SELECT phase, session_json
            FROM recommendation_sessions
            WHERE session_id = ?
            """,
            (session.session_id,),
        ).fetchone()
        assert row["phase"] == "searching"
        assert "希望故事节奏轻快" in row["session_json"]
    finally:
        db.close()


def test_sqlite_repository_upserts_and_deletes_session(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        repository = db.recommendation_session_repository
        session = complex_session()
        repository.save(session)
        completed = replace(
            session,
            phase=RecommendationAgentPhase.COMPLETED,
            tool_call_count=2,
            recommended_catalog_ids=("cam-jansen",),
            selected_catalog_id="cam-jansen",
        )

        repository.save(completed)

        assert repository.load(session.session_id) == completed
        assert repository.delete(session.session_id) is True
        assert repository.delete(session.session_id) is False
        assert repository.load(session.session_id) is None
    finally:
        db.close()


def test_app_db_exposes_recommendation_session_repository_port(tmp_path):
    db = AppDB(tmp_path / "app.db")
    try:
        assert isinstance(
            db.recommendation_session_repository,
            SQLiteRecommendationSessionRepository,
        )
        assert isinstance(
            db.recommendation_session_repository,
            RecommendationSessionRepository,
        )
    finally:
        db.close()
