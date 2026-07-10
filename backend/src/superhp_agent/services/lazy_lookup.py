"""Lazy lifecycle wrapper for profile-specific word lookup services.

This wrapper caches one WordLookupService per profile and delays provider
creation until lookup is used. It does not read Settings, build concrete
providers, expose HTTP DTOs, or participate in guided-flow routing.
"""

from collections.abc import Callable

from superhp_agent.ports.llm import LLMProvider
from superhp_agent.profiles import ProfileRegistry
from superhp_agent.services.lookup import WordLookupService


class LazyLookupService:
    """Build profile-specific lookup services only when first requested."""

    def __init__(
        self,
        provider_factory: Callable[[], LLMProvider],
        *,
        profile_registry: ProfileRegistry,
    ):
        self.provider_factory = provider_factory
        self.profile_registry = profile_registry
        self._services: dict[str, WordLookupService] = {}

    def _get_service(self, profile_id: str | None = None) -> WordLookupService:
        profile = self.profile_registry.get(profile_id)
        if profile.id not in self._services:
            self._services[profile.id] = WordLookupService(
                self.provider_factory(),
                profile=profile,
            )
        return self._services[profile.id]

    async def lookup(
        self,
        word: str,
        sentence: str,
        *,
        profile_id: str | None = None,
    ) -> dict:
        return await self._get_service(profile_id).lookup(word, sentence)
