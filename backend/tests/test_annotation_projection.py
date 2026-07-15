"""Tests for safe item-level projection onto immutable source text."""

from superhp_agent.contracts import AnnotationCandidate
from superhp_agent.profiles.annotation_projection import project_annotation_candidates

ALLOWED_POS = frozenset({"noun", "verb", "adjective", "adverb", "phrase", "other"})


def candidate(source, translation="译文", *, pos="noun", prefix="", suffix=""):
    return AnnotationCandidate(
        source=source,
        translation=translation,
        pos=pos,
        prefix=prefix,
        suffix=suffix,
    )


def test_projection_rebuilds_text_from_original_source():
    source = "Harry raised his wand, but the door stayed shut."

    result = project_annotation_candidates(
        source,
        [candidate("wand", "魔杖")],
        allowed_pos=ALLOWED_POS,
    )

    assert result.annotated_text == "Harry raised his [[wand|魔杖|noun]], but the door stayed shut."
    assert result.items[0].word == "wand"
    assert result.rejections == []


def test_projection_uses_anchors_to_disambiguate_repeated_source():
    source = "The door opened, then the second door slammed shut."

    result = project_annotation_candidates(
        source,
        [candidate("door", prefix="the second ", suffix=" slammed")],
        allowed_pos=ALLOWED_POS,
    )

    assert result.annotated_text == "The door opened, then the second [[door|译文|noun]] slammed shut."


def test_projection_rejects_ambiguous_item_without_losing_valid_items():
    source = "A wand lay beside another wand and a cloak."

    result = project_annotation_candidates(
        source,
        [candidate("wand"), candidate("cloak", "斗篷")],
        allowed_pos=ALLOWED_POS,
    )

    assert result.annotated_text == "A wand lay beside another wand and a [[cloak|斗篷|noun]]."
    assert [item.word for item in result.items] == ["cloak"]
    assert [(issue.candidate_index, issue.code) for issue in result.rejections] == [
        (1, "ambiguous_source")
    ]


def test_projection_normalizes_pos_and_rejects_only_overlapping_item():
    source = "He muttered under his breath."

    result = project_annotation_candidates(
        source,
        [
            candidate("muttered under his breath", "低声嘟囔", pos="unexpected"),
            candidate("under his breath", "低声地", pos="phrase"),
        ],
        allowed_pos=ALLOWED_POS,
    )

    assert result.annotated_text == "He [[muttered under his breath|低声嘟囔|other]]."
    assert result.items[0].pos == "other"
    assert result.rejections[0].code == "overlapping_source"


def test_projection_rejects_invalid_fields_independently():
    source = "A wand and a cloak."

    result = project_annotation_candidates(
        source,
        [
            candidate("wand", ""),
            candidate("cloak", "斗|篷"),
        ],
        allowed_pos=ALLOWED_POS,
    )

    assert result.annotated_text == source
    assert [issue.code for issue in result.rejections] == [
        "empty_translation",
        "reserved_translation_character",
    ]
