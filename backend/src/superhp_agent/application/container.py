"""Application composition root for long-lived backend capabilities.

The container owns concrete construction and dependency wiring. It does not
define FastAPI routes, process WebSocket messages, execute actions, or contain
business rules; Transport receives the assembled capabilities from here.
"""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.artifacts import AnnotatedCopyStore
from superhp_agent.config import Settings, get_settings
from superhp_agent.corpus import CorpusStore
from superhp_agent.memory import ReadingMemoryStore
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
from superhp_agent.storage import AppDB
from superhp_agent.storage.sqlite import (
    SQLiteBookmarkRepository,
    SQLiteVocabularyRepository,
)


@dataclass
class AppContainer:
    """Concrete capabilities shared by HTTP and WebSocket transports."""

    settings: Settings
    profile_registry: ProfileRegistry
    default_profile: AnnotationProfile
    corpus: CorpusStore
    memory_store: ReadingMemoryStore
    db: AppDB
    vocabulary_repository: SQLiteVocabularyRepository
    bookmark_repository: SQLiteBookmarkRepository
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
    memory_store = ReadingMemoryStore(
        resolved_settings.reading_memory_path,
        resolved_settings.event_log_path,
    )
    db = AppDB(resolved_settings.db_path)
    vocabulary_repository = db.vocabulary_repository
    bookmark_repository = db.bookmark_repository
    annotated_copies = AnnotatedCopyStore(resolved_settings.annotated_dir)

    def provider_factory():
        return make_provider(resolved_settings)

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
        memory_store,
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
        memory_store=memory_store,
        db=db,
        vocabulary_repository=vocabulary_repository,
        bookmark_repository=bookmark_repository,
        annotated_copies=annotated_copies,
        annotator_service=annotator_service,
        lookup_service=lookup_service,
        state_reader=state_reader,
        flow_router=flow_router,
    )
