"""Built-in text annotation profiles."""

from superhp_agent.profiles.base import AnnotationItem, AnnotationProfile, CardCopy
from superhp_agent.profiles.english_novel import EnglishNovelProfile
from superhp_agent.profiles.registry import ProfileRegistry, create_default_registry

__all__ = [
    "AnnotationItem",
    "AnnotationProfile",
    "CardCopy",
    "EnglishNovelProfile",
    "ProfileRegistry",
    "create_default_registry",
]

