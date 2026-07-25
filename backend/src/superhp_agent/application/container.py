"""Application composition root for long-lived backend capabilities.

The container owns concrete construction and dependency wiring. It does not
define FastAPI routes, process WebSocket messages, execute actions, or contain
business rules; Transport receives the assembled capabilities from here.
"""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.agent_tools import (
    BookCatalogSearchTool,
    PresentBookRecommendationsTool,
    ToolRegistry,
)
from superhp_agent.agents import BookRecommendationAgent, RecommendationContextBuilder
from superhp_agent.application.recommendation_runner import (
    RecommendationAgentRunner,
)
from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.config import Settings, get_settings
from superhp_agent.corpus import CorpusStore
from superhp_agent.event_log import EventLogStore
from superhp_agent.library_catalog import LibraryCatalogStore
from superhp_agent.profiles import (
    AnnotationProfile,
    ProfileRegistry,
    create_default_registry,
)
from superhp_agent.providers.factory import make_provider
from superhp_agent.runtime import (
    ReadingCardBuilder,
    ReadingFlowRouter,
    ReadingStateReader,
)
from superhp_agent.services.annotator import LazyAnnotatorService
from superhp_agent.services.lazy_lookup import LazyLookupService
from superhp_agent.services.recommendation import RecommendationCandidateService
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import (
    SQLiteBookDifficultyCatalog,
    SQLiteBookmarkRepository,
    SQLiteReadingProgressRepository,
    SQLiteRecommendationSessionRepository,
    SQLiteVocabularyRepository,
)


@dataclass
class AppContainer:
    """Concrete capabilities shared by HTTP and WebSocket transports."""

    settings: Settings
    profile_registry: ProfileRegistry
    default_profile: AnnotationProfile
    corpus: CorpusStore
    library_catalog: LibraryCatalogStore
    event_log_store: EventLogStore
    db: AppDB
    vocabulary_repository: SQLiteVocabularyRepository
    bookmark_repository: SQLiteBookmarkRepository
    reading_progress_repository: SQLiteReadingProgressRepository
    book_difficulty_catalog: SQLiteBookDifficultyCatalog
    recommendation_session_repository: SQLiteRecommendationSessionRepository
    recommendation_candidate_service: RecommendationCandidateService
    book_catalog_search_tool: BookCatalogSearchTool
    present_book_recommendations_tool: PresentBookRecommendationsTool
    recommendation_tool_registry: ToolRegistry
    recommendation_context_builder: RecommendationContextBuilder
    recommendation_agent_runner: RecommendationAgentRunner
    annotated_copies: AnnotatedCopyStore
    annotator_service: LazyAnnotatorService
    lookup_service: LazyLookupService
    state_reader: ReadingStateReader
    flow_router: ReadingFlowRouter

    def close(self) -> None:
        """Release resources owned by the composition root."""
        self.db.close()


def build_container(settings: Settings | None = None) -> AppContainer:
    """Construct the backend object graph from resolved Settings."""
    resolved_settings = settings or get_settings()
    profile_registry = create_default_registry(resolved_settings.default_profile_id)
    default_profile = profile_registry.get()
    corpus = CorpusStore(
        resolved_settings.corpus_dir,
        default_profile_id=resolved_settings.default_profile_id,
    )
    library_catalog = LibraryCatalogStore(resolved_settings.corpus_dir / "catalog.yaml")
    for unit in corpus.list_units():
        try:
            profile_registry.get(unit.profile_id)
        except ValueError as exc:
            raise ValueError(
                f"Unknown profile in reading unit {unit.id}: {unit.profile_id}"
            ) from exc
    library_catalog.validate(profile_registry)
    event_log_store = EventLogStore(resolved_settings.event_log_path)
    db = AppDB(resolved_settings.db_path)
    vocabulary_repository = db.vocabulary_repository
    bookmark_repository = db.bookmark_repository
    reading_progress_repository = db.reading_progress_repository
    book_difficulty_catalog = db.book_difficulty_catalog
    recommendation_session_repository = db.recommendation_session_repository
    recommendation_candidate_service = RecommendationCandidateService(
        book_difficulty_catalog
    )
    book_catalog_search_tool = BookCatalogSearchTool(recommendation_candidate_service)
    present_book_recommendations_tool = PresentBookRecommendationsTool()
    recommendation_tool_registry = ToolRegistry(
        (
            book_catalog_search_tool,
            present_book_recommendations_tool,
        )
    )
    recommendation_context_builder = RecommendationContextBuilder()
    annotated_copies = AnnotatedCopyStore(resolved_settings.annotated_dir)

    def provider_factory():
        return make_provider(resolved_settings)

    recommendation_agent_runner = RecommendationAgentRunner(
        lambda: BookRecommendationAgent(
            provider_factory(),
            recommendation_context_builder,
            recommendation_tool_registry,
        ),
        recommendation_session_repository,
    )
    annotator_service = LazyAnnotatorService(
        provider_factory,
        profile=default_profile,
        profile_registry=profile_registry,
        max_chunk_words=resolved_settings.annotation_max_chunk_words,
        max_concurrency=resolved_settings.annotation_max_concurrency,
    )
    lookup_service = LazyLookupService(
        provider_factory,
        profile_registry=profile_registry,
    )
    state_reader = ReadingStateReader(
        corpus,
        annotated_copies,
        reading_progress_repository,
        vocabulary_repository,
    )
    flow_router = ReadingFlowRouter(
        state_reader,
        card_builder=ReadingCardBuilder(
            default_profile.card_copy,
            profile_registry=profile_registry,
        ),
    )
    return AppContainer(
        settings=resolved_settings,
        profile_registry=profile_registry,
        default_profile=default_profile,
        corpus=corpus,
        library_catalog=library_catalog,
        event_log_store=event_log_store,
        db=db,
        vocabulary_repository=vocabulary_repository,
        bookmark_repository=bookmark_repository,
        reading_progress_repository=reading_progress_repository,
        book_difficulty_catalog=book_difficulty_catalog,
        recommendation_session_repository=recommendation_session_repository,
        recommendation_candidate_service=recommendation_candidate_service,
        book_catalog_search_tool=book_catalog_search_tool,
        present_book_recommendations_tool=present_book_recommendations_tool,
        recommendation_tool_registry=recommendation_tool_registry,
        recommendation_context_builder=recommendation_context_builder,
        recommendation_agent_runner=recommendation_agent_runner,
        annotated_copies=annotated_copies,
        annotator_service=annotator_service,
        lookup_service=lookup_service,
        state_reader=state_reader,
        flow_router=flow_router,
    )
