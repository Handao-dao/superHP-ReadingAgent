"""Registry for text-learning annotation profiles."""

from __future__ import annotations

from dataclasses import dataclass

from superhp_agent.profiles.base import AnnotationProfile


class UnknownProfileError(ValueError):
    """Raised when configuration or input names an unregistered Profile."""

    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        super().__init__(f"Unknown profile id: {profile_id}")


@dataclass(frozen=True)
class ProfileRegistry:
    """Small in-process registry for configured annotation profiles."""

    profiles: dict[str, AnnotationProfile]
    default_profile_id: str = "english_novel"

    def __post_init__(self) -> None:
        if self.default_profile_id not in self.profiles:
            raise UnknownProfileError(self.default_profile_id)
        for profile_id, profile in self.profiles.items():
            if profile.id != profile_id:
                raise ValueError(
                    f"Profile registry key does not match profile id: {profile_id} != {profile.id}"
                )

    def get(self, profile_id: str | None = None) -> AnnotationProfile:
        key = profile_id or self.default_profile_id
        profile = self.profiles.get(key)
        if profile is not None:
            return profile
        raise UnknownProfileError(key)

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
        default_profile_id=default_profile_id,
    )
