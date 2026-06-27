"""Registry for text-learning annotation profiles."""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.profiles.base import AnnotationProfile


@dataclass(frozen=True)
class ProfileRegistry:
    """Small in-process registry for configured annotation profiles."""

    profiles: dict[str, AnnotationProfile]
    default_profile_id: str = "english_novel"

    def get(self, profile_id: str | None = None) -> AnnotationProfile:
        key = profile_id or self.default_profile_id
        profile = self.profiles.get(key)
        if profile is not None:
            return profile
        return self.profiles[self.default_profile_id]

    def list_profiles(self) -> list[AnnotationProfile]:
        """Return profiles with the default first, then stable id order."""
        profiles = sorted(self.profiles.values(), key=lambda profile: profile.id)
        return sorted(profiles, key=lambda profile: profile.id != self.default_profile_id)


def create_default_registry(default_profile_id: str = "english_novel") -> ProfileRegistry:
    from superhp_agent.profiles.classical_chinese import ClassicalChineseProfile
    from superhp_agent.profiles.english_novel import EnglishNovelProfile

    classical_chinese = ClassicalChineseProfile()
    english_novel = EnglishNovelProfile()
    profiles = {
        classical_chinese.id: classical_chinese,
        english_novel.id: english_novel,
    }
    return ProfileRegistry(
        profiles=profiles,
        default_profile_id=default_profile_id if default_profile_id in profiles else english_novel.id,
    )
