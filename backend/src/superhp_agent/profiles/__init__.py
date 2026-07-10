"""Built-in text annotation profiles."""

from superhp_agent.contracts.annotation import AnnotationItem
from superhp_agent.profiles.base import AnnotationProfile, CardCopy
from superhp_agent.profiles.classical_chinese import ClassicalChineseProfile
from superhp_agent.profiles.english_novel import EnglishNovelProfile
from superhp_agent.profiles.registry import ProfileRegistry, create_default_registry

__all__ = [
    "AnnotationItem",
    "AnnotationProfile",
    "CardCopy",
    "ClassicalChineseProfile",
    "EnglishNovelProfile",
    "ProfileRegistry",
    "create_default_registry",
]
