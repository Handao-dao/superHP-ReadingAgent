"""Application composition root for long-lived backend capabilities.

The container owns concrete construction and dependency wiring. It does not
define FastAPI routes, process WebSocket messages, execute actions, or contain
business rules; Transport receives the assembled capabilities from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from superhp_agent.agent_tools.book_catalog import BookCatalogSearchTool
from superhp_agent.agent_tools.recommendation_result import (
    PresentBookRecommendationsTool,
    SelectRecommendedBookTool,
)
from superhp_agent.agent_tools.registry import (
    ToolRegistry,
)
from superhp_agent.agents import (
    BookRecommendationAgent,
    ReadingCompanionAgent,
    ReadingCompanionContextBuilder,
    RecommendationContextBuilder,
)
from superhp_agent.application.chapter_checkpoints import ChapterCheckpointRecorder
from superhp_agent.application.difficulty_handoff import (
    DifficultyRecommendationHandoffBuilder,
)
from superhp_agent.application.manual_reading_companion import (
    ManualReadingCompanionRunner,
)
from superhp_agent.application.previous_chapter_search import (
    PreviousChapterSearchService,
)
from superhp_agent.application.previous_reading_scope import (
    PreviousReadingScopeBuilder,
)
from superhp_agent.application.reading_adaptation_evaluator import (
    ReadingAdaptationEvaluator,
)
from superhp_agent.application.reading_companion_sessions import (
    ReadingCompanionSessionCoordinator,
)
from superhp_agent.application.reading_difficulty_prompts import (
    ReadingDifficultyPromptCoordinator,
)
from superhp_agent.application.reading_monitor import ReadingDifficultyMonitor
from superhp_agent.application.recommendation_runner import (
    RecommendationAgentRunner,
)
from superhp_agent.application.vocabulary_history_search import (
    VocabularyHistorySearchService,
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
    SQLiteChapterReadingCheckpointRepository,
    SQLiteConversationMemoryRepository,
    SQLiteReadingCompanionRepository,
    SQLiteReadingDifficultyPromptRepository,
    SQLiteReadingLookupRepository,
    SQLiteReadingProgressRepository,
    SQLiteReadingSupportRepository,
    SQLiteRecommendationSessionRepository,
    SQLiteVocabularyHistoryRepository,
    SQLiteVocabularyRepository,
)

if TYPE_CHECKING:
    from superhp_agent.agent_tools.reading_history import (
        PreviousChapterSearchTool,
        VocabularyHistorySearchTool,
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
    vocabulary_history_repository: SQLiteVocabularyHistoryRepository
    bookmark_repository: SQLiteBookmarkRepository
    reading_progress_repository: SQLiteReadingProgressRepository
    reading_lookup_repository: SQLiteReadingLookupRepository
    reading_difficulty_prompt_repository: (
        SQLiteReadingDifficultyPromptRepository
    )
    reading_support_repository: SQLiteReadingSupportRepository
    chapter_checkpoint_repository: SQLiteChapterReadingCheckpointRepository
    chapter_checkpoint_recorder: ChapterCheckpointRecorder
    reading_adaptation_evaluator: ReadingAdaptationEvaluator
    reading_difficulty_prompt_coordinator: (
        ReadingDifficultyPromptCoordinator
    )
    reading_difficulty_monitor: ReadingDifficultyMonitor
    difficulty_handoff_builder: DifficultyRecommendationHandoffBuilder
    book_difficulty_catalog: SQLiteBookDifficultyCatalog
    recommendation_session_repository: SQLiteRecommendationSessionRepository
    reading_companion_repository: SQLiteReadingCompanionRepository
    conversation_memory_repository: SQLiteConversationMemoryRepository
    recommendation_candidate_service: RecommendationCandidateService
    previous_reading_scope_builder: PreviousReadingScopeBuilder
    previous_chapter_search_service: PreviousChapterSearchService
    vocabulary_history_search_service: VocabularyHistorySearchService
    book_catalog_search_tool: BookCatalogSearchTool
    previous_chapter_search_tool: PreviousChapterSearchTool
    vocabulary_history_search_tool: VocabularyHistorySearchTool
    present_book_recommendations_tool: PresentBookRecommendationsTool
    select_recommended_book_tool: SelectRecommendedBookTool
    agent_tool_registry: ToolRegistry
    recommendation_context_builder: RecommendationContextBuilder
    recommendation_agent_runner: RecommendationAgentRunner
    reading_companion_context_builder: ReadingCompanionContextBuilder
    manual_reading_companion_runner: ManualReadingCompanionRunner
    reading_companion_session_coordinator: (
        ReadingCompanionSessionCoordinator
    )
    annotated_copies: AnnotatedCopyStore
    annotator_service: LazyAnnotatorService
    lookup_service: LazyLookupService
    state_reader: ReadingStateReader
    flow_router: ReadingFlowRouter

    @property
    def recommendation_tool_registry(self) -> ToolRegistry:
        """Compatibility alias for the now shared explicit ToolRegistry."""
        return self.agent_tool_registry

    def close(self) -> None:
        """Release resources owned by the composition root."""
        self.db.close()


def build_container(settings: Settings | None = None) -> AppContainer:
    """Construct the backend object graph from resolved Settings."""
    from superhp_agent.agent_tools.reading_history import (
        PreviousChapterSearchTool,
        VocabularyHistorySearchTool,
    )

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
    vocabulary_history_repository = db.vocabulary_history_repository
    bookmark_repository = db.bookmark_repository
    reading_progress_repository = db.reading_progress_repository
    reading_lookup_repository = db.reading_lookup_repository
    reading_difficulty_prompt_repository = (
        db.reading_difficulty_prompt_repository
    )
    reading_support_repository = db.reading_support_repository
    chapter_checkpoint_repository = db.chapter_checkpoint_repository
    reading_difficulty_monitor = ReadingDifficultyMonitor(
        corpus,
        reading_progress_repository,
        reading_lookup_repository,
    )
    book_difficulty_catalog = db.book_difficulty_catalog
    difficulty_handoff_builder = DifficultyRecommendationHandoffBuilder(
        corpus,
        library_catalog,
        book_difficulty_catalog,
        reading_progress_repository,
    )
    recommendation_session_repository = db.recommendation_session_repository
    reading_companion_repository = db.reading_companion_repository
    conversation_memory_repository = db.conversation_memory_repository
    recommendation_candidate_service = RecommendationCandidateService(
        book_difficulty_catalog
    )
    previous_reading_scope_builder = PreviousReadingScopeBuilder(
        corpus,
        chapter_checkpoint_repository,
    )
    previous_chapter_search_service = PreviousChapterSearchService(corpus)
    vocabulary_history_search_service = VocabularyHistorySearchService(
        vocabulary_history_repository
    )
    book_catalog_search_tool = BookCatalogSearchTool(recommendation_candidate_service)
    previous_chapter_search_tool = PreviousChapterSearchTool(
        previous_chapter_search_service
    )
    vocabulary_history_search_tool = VocabularyHistorySearchTool(
        vocabulary_history_search_service
    )
    present_book_recommendations_tool = PresentBookRecommendationsTool()
    select_recommended_book_tool = SelectRecommendedBookTool()
    agent_tool_registry = ToolRegistry(
        (
            book_catalog_search_tool,
            present_book_recommendations_tool,
            select_recommended_book_tool,
            previous_chapter_search_tool,
            vocabulary_history_search_tool,
        )
    )
    recommendation_context_builder = RecommendationContextBuilder()
    reading_companion_context_builder = ReadingCompanionContextBuilder()
    annotated_copies = AnnotatedCopyStore(resolved_settings.annotated_dir)
    chapter_checkpoint_recorder = ChapterCheckpointRecorder(
        corpus,
        reading_progress_repository,
        reading_lookup_repository,
        chapter_checkpoint_repository,
        annotated_copies,
    )
    reading_adaptation_evaluator = ReadingAdaptationEvaluator(
        chapter_checkpoint_repository,
        reading_support_repository,
        prompt_repository=reading_difficulty_prompt_repository,
    )
    reading_difficulty_prompt_coordinator = (
        ReadingDifficultyPromptCoordinator(
            reading_difficulty_prompt_repository,
            reading_support_repository,
        )
    )

    def provider_factory():
        return make_provider(resolved_settings)

    recommendation_agent_runner = RecommendationAgentRunner(
        lambda: BookRecommendationAgent(
            provider_factory(),
            recommendation_context_builder,
            agent_tool_registry,
        ),
        recommendation_session_repository,
    )
    manual_reading_companion_runner = ManualReadingCompanionRunner(
        corpus,
        previous_reading_scope_builder,
        lambda: ReadingCompanionAgent(
            provider_factory(),
            reading_companion_context_builder,
            agent_tool_registry,
        ),
    )
    reading_companion_session_coordinator = (
        ReadingCompanionSessionCoordinator(
            manual_reading_companion_runner,
            reading_companion_repository,
        )
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
        vocabulary_history_repository=vocabulary_history_repository,
        bookmark_repository=bookmark_repository,
        reading_progress_repository=reading_progress_repository,
        reading_lookup_repository=reading_lookup_repository,
        reading_difficulty_prompt_repository=(
            reading_difficulty_prompt_repository
        ),
        reading_support_repository=reading_support_repository,
        chapter_checkpoint_repository=chapter_checkpoint_repository,
        chapter_checkpoint_recorder=chapter_checkpoint_recorder,
        reading_adaptation_evaluator=reading_adaptation_evaluator,
        reading_difficulty_prompt_coordinator=(
            reading_difficulty_prompt_coordinator
        ),
        reading_difficulty_monitor=reading_difficulty_monitor,
        difficulty_handoff_builder=difficulty_handoff_builder,
        book_difficulty_catalog=book_difficulty_catalog,
        recommendation_session_repository=recommendation_session_repository,
        reading_companion_repository=reading_companion_repository,
        conversation_memory_repository=conversation_memory_repository,
        recommendation_candidate_service=recommendation_candidate_service,
        previous_reading_scope_builder=previous_reading_scope_builder,
        previous_chapter_search_service=previous_chapter_search_service,
        vocabulary_history_search_service=vocabulary_history_search_service,
        book_catalog_search_tool=book_catalog_search_tool,
        previous_chapter_search_tool=previous_chapter_search_tool,
        vocabulary_history_search_tool=vocabulary_history_search_tool,
        present_book_recommendations_tool=present_book_recommendations_tool,
        select_recommended_book_tool=select_recommended_book_tool,
        agent_tool_registry=agent_tool_registry,
        recommendation_context_builder=recommendation_context_builder,
        recommendation_agent_runner=recommendation_agent_runner,
        reading_companion_context_builder=(
            reading_companion_context_builder
        ),
        manual_reading_companion_runner=manual_reading_companion_runner,
        reading_companion_session_coordinator=(
            reading_companion_session_coordinator
        ),
        annotated_copies=annotated_copies,
        annotator_service=annotator_service,
        lookup_service=lookup_service,
        state_reader=state_reader,
        flow_router=flow_router,
    )
