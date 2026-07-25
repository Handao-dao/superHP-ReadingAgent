"""Import a pasted Lexile book list into the local recommendation catalog.

This is an explicit data-maintenance tool, not part of the application runtime.
It parses the user's source rows, optionally enriches them with public book
metadata, normalizes noisy subjects into a small style-tag vocabulary, and
replaces the disposable SQLite recommendation catalog in one transaction.

External metadata is advisory: the source Lexile value is never overwritten,
and low-confidence matches are kept in the report instead of being trusted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = BACKEND_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from superhp_agent.contracts.recommendation import (  # noqa: E402
    BookCandidate,
    BookDifficulty,
    BookEntryKind,
)
from superhp_agent.storage.database import SQLiteDatabase  # noqa: E402
from superhp_agent.storage.migrations import initialize_schema  # noqa: E402
from superhp_agent.storage.sqlite import SQLiteBookDifficultyCatalog  # noqa: E402

STYLE_TAGS = {
    "adventure",
    "animal_story",
    "biography",
    "classic",
    "coming_of_age",
    "crime",
    "dystopian",
    "fairy_tale",
    "family_friendship",
    "fantasy",
    "historical_fiction",
    "history",
    "horror",
    "humor",
    "mystery",
    "mythology",
    "nonfiction",
    "philosophy",
    "poetry",
    "realistic_fiction",
    "romance",
    "school_life",
    "science",
    "science_fiction",
    "short_stories",
    "writing_guide",
}

TITLE_CORRECTIONS = {
    "a z mysteris": "A to Z Mysteries",
    "arthur": "Arthur (Marc Brown series)",
    "famous five enid blyton": "The Famous Five",
    "famous dead peaple": "Famous Dead People",
    "five on a treasure island enid blyton": "Five on a Treasure Island",
    "hp": "Harry Potter",
    "hitler youth susan campbell bartoletti": "Hitler Youth",
    "lincoln a photo biography": "Lincoln: A Photobiography",
    "lord brock tree": "The Book of Three",
    "number the stars lowry loisv": "Number the Stars",
    "phineas and ferb wiki": "Phineas and Ferb",
    "rascal north sterling": "Rascal",
    "sarab plain and tall skylark and caleb s story": (
        "Sarah, Plain and Tall series"
    ),
    "the 39 clues 39": "The 39 Clues",
    "the big friendly giant": "The BFG",
    "the black cauldron book 2": "The Black Cauldron",
    "feathers": "Feathers (Jacqueline Woodson)",
    "the king": "King of the Wind",
    "the mini pins": "The Minpins",
    "the mysterious adventures of sherlock holmes": (
        "The Mysterious Adventures of Sherlock Holmes"
    ),
    "the secret seven 7": "The Secret Seven",
    "the zack files 01 great grandpa s in the litter": (
        "The Zack Files: Great-Grandpa's in the Litter Box"
    ),
    "were puppy on holiday": "Werepuppy on Holiday",
    "winnie": "Winnie the Witch",
    "worth": "Worth (A. LaFaye)",
}

# These recognizable titles provide deterministic anchors when public search
# returns a movie, workbook, unrelated namesake, or no usable category.
TITLE_TAG_OVERRIDES: dict[str, tuple[str, ...]] = {
    "101 ways to improve your grammar skills": ("nonfiction", "writing_guide"),
    "1001 unbelievable facts": ("nonfiction", "science"),
    "a short history of nearly everything": ("nonfiction", "science"),
    "a bear called paddington": ("animal_story", "humor", "classic"),
    "a christmas memory": ("family_friendship", "classic"),
    "a little princess": ("classic", "family_friendship", "school_life"),
    "a midsummer night s dream": ("classic", "fantasy", "romance"),
    "a to z mysteries": ("mystery", "adventure"),
    "alice s adventures in wonderland": ("fantasy", "adventure", "classic"),
    "amelia bedelia": ("humor", "family_friendship"),
    "anne of green gables": ("classic", "coming_of_age", "family_friendship"),
    "animal farm": ("classic", "dystopian"),
    "a wrinkle in time": ("fantasy", "science_fiction", "adventure"),
    "arthur marc brown series": (
        "school_life",
        "family_friendship",
        "animal_story",
    ),
    "cam jansen": ("mystery", "school_life"),
    "captain underpants": ("humor", "school_life", "adventure"),
    "charlie and the chocolate factory": ("fantasy", "humor", "adventure"),
    "chronicles of narnia": ("fantasy", "adventure", "classic"),
    "charlottes web": ("animal_story", "family_friendship", "classic"),
    "daddy long legs": ("classic", "romance", "coming_of_age"),
    "dear dumb diary": ("humor", "school_life"),
    "dragon masters": ("fantasy", "adventure"),
    "dragonwings": ("historical_fiction", "family_friendship", "coming_of_age"),
    "eerie elementary": ("horror", "fantasy", "school_life"),
    "esio trot": ("humor", "romance", "animal_story"),
    "encyclopedia brown mystery series": ("mystery", "school_life"),
    "eragon": ("fantasy", "adventure"),
    "famous dead people": ("nonfiction", "biography", "history"),
    "fantastic mr fox": ("animal_story", "fantasy", "adventure"),
    "flatland": ("classic", "science_fiction"),
    "flora and ulysses": ("fantasy", "humor", "family_friendship"),
    "george s marvellous medicine": ("fantasy", "humor"),
    "geronimo stilton": ("adventure", "humor", "mystery"),
    "going solo": ("biography", "nonfiction", "historical_fiction"),
    "gone away lake": ("mystery", "adventure", "family_friendship"),
    "gone with the wind": ("historical_fiction", "romance", "classic"),
    "goosebumps": ("horror", "fantasy", "adventure"),
    "harry potter": ("fantasy", "adventure", "school_life"),
    "henry and mudge": ("animal_story", "family_friendship", "realistic_fiction"),
    "heidi": ("classic", "family_friendship", "coming_of_age"),
    "hitler youth": ("nonfiction", "history", "biography"),
    "horrible science": ("nonfiction", "science", "humor"),
    "horrid henry": ("humor", "family_friendship"),
    "hypno hounds": ("mystery", "humor", "animal_story"),
    "jigsaw jones mystery": ("mystery", "school_life"),
    "king of the wind": ("animal_story", "historical_fiction", "classic"),
    "kira kira": ("historical_fiction", "family_friendship", "coming_of_age"),
    "lincoln a photobiography": ("nonfiction", "biography", "history"),
    "magic school bus": ("science", "adventure", "nonfiction"),
    "magic tree house": ("adventure", "fantasy", "historical_fiction"),
    "maniac magee": ("realistic_fiction", "coming_of_age", "family_friendship"),
    "mr popper s penguins": ("animal_story", "humor", "classic"),
    "museum of thieves": ("fantasy", "adventure"),
    "my father s dragon": ("fantasy", "adventure", "animal_story"),
    "my weird school": ("school_life", "humor"),
    "nate the great": ("mystery", "humor"),
    "of mice and men": ("classic", "realistic_fiction", "historical_fiction"),
    "over to you a collection of short stories": (
        "short_stories",
        "historical_fiction",
        "adventure",
    ),
    "phineas and ferb": ("humor", "science_fiction", "family_friendship"),
    "pinocchio": ("classic", "fantasy", "fairy_tale"),
    "pippi on the run": ("adventure", "humor"),
    "pippi longstocking": ("classic", "humor", "adventure"),
    "pride and prejudice": ("classic", "romance"),
    "rascal": ("biography", "nonfiction", "animal_story"),
    "revolting rhymes and dirty beasts": ("poetry", "humor", "fairy_tale"),
    "roll of thunder hear my cry": (
        "historical_fiction",
        "family_friendship",
        "coming_of_age",
    ),
    "sarah plain and tall series": (
        "historical_fiction",
        "family_friendship",
        "realistic_fiction",
    ),
    "s o s titanic": ("historical_fiction", "adventure"),
    "shiloh": ("animal_story", "family_friendship", "realistic_fiction"),
    "sideways stories from wayside school": ("school_life", "humor"),
    "sounder": ("animal_story", "historical_fiction", "family_friendship"),
    "stuart little": ("fantasy", "animal_story", "adventure"),
    "percy jackson": ("fantasy", "mythology", "adventure"),
    "the 39 clues": ("mystery", "adventure"),
    "the bfg": ("fantasy", "adventure", "humor"),
    "the black cauldron": ("fantasy", "adventure"),
    "the book of three": ("fantasy", "adventure"),
    "the borrowers": ("fantasy", "adventure", "classic"),
    "the boxcar children": ("mystery", "adventure", "family_friendship"),
    "the bourne": ("crime", "mystery", "adventure"),
    "the giver": ("dystopian", "science_fiction", "coming_of_age"),
    "the hitchhiker s guide to the galaxy": (
        "science_fiction",
        "humor",
        "adventure",
    ),
    "the history of science": ("nonfiction", "science"),
    "the hobbit": ("fantasy", "adventure", "classic"),
    "the lord of the rings trilogy": ("fantasy", "adventure", "classic"),
    "the mysterious adventures of sherlock holmes": (
        "mystery",
        "crime",
        "classic",
    ),
    "the notebook of doom": ("horror", "fantasy", "humor"),
    "the nutcracker and the mouse king": ("fairy_tale", "fantasy", "classic"),
    "the secret garden": ("classic", "mystery", "coming_of_age"),
    "the secret seven": ("mystery", "adventure"),
    "the cricket in times square": (
        "animal_story",
        "family_friendship",
        "classic",
    ),
    "the dark is rising": ("fantasy", "adventure"),
    "the great blue yonder": ("fantasy", "coming_of_age"),
    "the last polar bears": ("animal_story", "humor", "adventure"),
    "the penderwicks": ("family_friendship", "realistic_fiction", "humor"),
    "the railway children": ("classic", "family_friendship", "adventure"),
    "the ruby in the smoke": ("mystery", "historical_fiction", "crime"),
    "the wizard of oz": ("fantasy", "adventure", "classic"),
    "the snow queen": ("fairy_tale", "fantasy", "classic"),
    "the tao of pooh": ("nonfiction", "philosophy", "classic"),
    "the trumpet of the swan": ("animal_story", "fantasy", "classic"),
    "the water babies": ("fantasy", "fairy_tale", "classic"),
    "the wind in the willows": ("animal_story", "classic", "adventure"),
    "the witch of blackbird pond": (
        "historical_fiction",
        "coming_of_age",
        "romance",
    ),
    "the witches": ("fantasy", "horror", "humor"),
    "the wonderful story of henry sugar and six more": (
        "short_stories",
        "fantasy",
    ),
    "to kill a mockingbird": ("classic", "historical_fiction", "coming_of_age"),
    "tom sawyer and huckleberry finn": (
        "classic",
        "adventure",
        "coming_of_age",
    ),
    "treasure island": ("classic", "adventure"),
    "ultimate writing guide for students": ("nonfiction", "writing_guide"),
    "warriors": ("animal_story", "fantasy", "adventure"),
    "winnie the witch": ("fantasy", "humor"),
    "worth a lafaye": (
        "historical_fiction",
        "realistic_fiction",
        "family_friendship",
    ),
    "feathers jacqueline woodson": (
        "realistic_fiction",
        "family_friendship",
        "coming_of_age",
    ),
    "island of the blue dolphins": (
        "adventure",
        "historical_fiction",
        "coming_of_age",
    ),
    "little house in the big woods": (
        "historical_fiction",
        "family_friendship",
        "classic",
    ),
    "robinson crusoe": ("classic", "adventure", "historical_fiction"),
}

AUTHOR_OVERRIDES = {
    "encyclopedia brown mystery series": "Donald J. Sobol",
    "feathers jacqueline woodson": "Jacqueline Woodson",
    "over to you a collection of short stories": "Roald Dahl",
    "pippi on the run": "Astrid Lindgren",
    "sarah plain and tall series": "Patricia MacLachlan",
    "warriors": "Erin Hunter",
    "worth a lafaye": "A. LaFaye",
}

TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        r"\b(detective|mystery|mysteries|sleuth|investigation|whodunit)\b",
        ("mystery",),
    ),
    (r"\b(crime|spy|spies|espionage|thriller)\b", ("crime",)),
    (
        r"\b(fantasy|magic|magical|witch|wizard|dragon|fairy|supernatural)\b",
        ("fantasy",),
    ),
    (
        r"\b(adventure|quest|journey|expedition|explorer|survival)\b",
        ("adventure",),
    ),
    (
        r"\b(science fiction|space|alien|time travel|interplanetary)\b",
        ("science_fiction",),
    ),
    (r"\b(horror|ghost|monster|scary|spooky|vampire)\b", ("horror",)),
    (r"\b(humou?r|funny|comic|comedy|joke|wacky)\b", ("humor",)),
    (
        r"\b(school|student|classroom|teacher|boarding school)\b",
        ("school_life",),
    ),
    (
        r"\b(friendship|family|siblings?|brothers?|sisters?|parents?)\b",
        ("family_friendship",),
    ),
    (
        r"\b(animals?|dogs?|cats?|horses?|wolves|rabbit|fox|penguin|bear)\b",
        ("animal_story",),
    ),
    (
        r"\b(historical fiction|world war|civil war|frontier|pioneer)\b",
        ("historical_fiction",),
    ),
    (
        r"\b(realistic fiction|social life|everyday life|domestic fiction)\b",
        ("realistic_fiction",),
    ),
    (r"\b(fairy tales?|folklore|folk tales?|princess)\b", ("fairy_tale",)),
    (r"\b(coming of age|bildungsroman|growing up)\b", ("coming_of_age",)),
    (r"\b(mythology|myths?|greek gods?)\b", ("mythology",)),
    (r"\b(dystopia|dystopian)\b", ("dystopian",)),
    (r"\b(romance|love stories)\b", ("romance",)),
    (
        r"\b(biography|autobiography|memoir|personal narratives?)\b",
        ("biography", "nonfiction"),
    ),
    (
        r"\b(nonfiction|facts|reference)\b",
        ("nonfiction",),
    ),
    (
        r"\b(science(?! fiction)|scientists?|nature|technology|experiments?)\b",
        ("science",),
    ),
    (
        r"\b(grammar|writing skills?|writing guide)\b",
        ("writing_guide", "nonfiction"),
    ),
    (
        r"\b(classic|classics|literary fiction|nineteenth century)\b",
        ("classic",),
    ),
)

TAG_PRIORITY = (
    "mystery",
    "crime",
    "fantasy",
    "mythology",
    "adventure",
    "science_fiction",
    "horror",
    "humor",
    "school_life",
    "family_friendship",
    "animal_story",
    "historical_fiction",
    "history",
    "realistic_fiction",
    "fairy_tale",
    "coming_of_age",
    "dystopian",
    "romance",
    "biography",
    "philosophy",
    "poetry",
    "short_stories",
    "science",
    "writing_guide",
    "nonfiction",
    "classic",
)


@dataclass(frozen=True)
class ParsedBook:
    """One source row after conservative structural cleanup."""

    source_index: int
    raw_text: str
    title_en: str
    search_title: str
    title_zh: str
    difficulty_min: int
    difficulty_max: int
    entry_kind: BookEntryKind


@dataclass(frozen=True)
class MetadataMatch:
    """Small provider-neutral metadata result used by the tag mapper."""

    source: str
    title: str
    authors: tuple[str, ...]
    subjects: tuple[str, ...]
    description: str
    confidence: float


@dataclass(frozen=True)
class ImportRecord:
    """Audit details for one imported row."""

    catalog_id: str
    source_index: int
    search_title: str
    matched_source: str
    matched_title: str
    match_confidence: float
    author: str
    tags: tuple[str, ...]
    warnings: tuple[str, ...]


def normalize_title(value: str) -> str:
    """Normalize a title for correction lookup, matching, and stable ids."""
    value = unicodedata.normalize("NFKD", value).casefold()
    value = value.replace("&", " and ")
    return " ".join(re.findall(r"[a-z0-9]+", value))


def parse_source_line(raw_text: str, source_index: int) -> ParsedBook:
    """Parse one ``Lexile + English title + optional Chinese title`` row."""
    raw_text = raw_text.strip()
    match = re.match(r"^(\d+)(?:\s*-\s*(\d+))?\s*L?\s*(.+)$", raw_text, re.I)
    if not match:
        raise ValueError(f"row {source_index}: unsupported Lexile prefix")

    minimum = int(match.group(1))
    maximum = int(match.group(2) or match.group(1))
    body = match.group(3).strip()
    cjk_match = re.search(r"[\u3400-\u9fff]", body)
    if cjk_match:
        title_en = body[: cjk_match.start()].strip(" -—《》")
        title_zh = body[cjk_match.start() :].strip()
    else:
        title_en = body
        title_zh = ""

    title_en = re.sub(r"\s+", " ", title_en).strip()
    normalized = normalize_title(title_en)
    search_title = TITLE_CORRECTIONS.get(normalized, title_en)
    title_zh = clean_chinese_title(title_zh)
    entry_kind = infer_entry_kind(raw_text, minimum, maximum)
    return ParsedBook(
        source_index=source_index,
        raw_text=raw_text,
        title_en=title_en,
        search_title=search_title,
        title_zh=title_zh,
        difficulty_min=minimum,
        difficulty_max=maximum,
        entry_kind=entry_kind,
    )


def clean_chinese_title(value: str) -> str:
    """Remove obvious award, author, and year notes from the Chinese title."""
    if not value:
        return ""
    value = re.split(
        r"(?:纽伯瑞|纽奖|罗尔德|罗德达尔|马克吐温|\b20\d{2}\b)",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    return value.strip(" 《》-—?？")


def infer_entry_kind(
    raw_text: str, minimum: int, maximum: int
) -> BookEntryKind:
    """Infer only broad catalog shape; ambiguity remains ``unknown``."""
    normalized = normalize_title(raw_text)
    if re.search(r"\b(collection|合集|短篇集)\b", raw_text, re.I):
        return BookEntryKind.COLLECTION
    if (
        minimum != maximum
        or re.search(r"\b(series|trilogy)\b", raw_text, re.I)
        or "系列" in raw_text
        or "三部曲" in raw_text
        or normalized in {"hp harry potter", "warriors"}
    ):
        return BookEntryKind.SERIES
    if "six more" in normalized or "adventures of sherlock holmes" in normalized:
        return BookEntryKind.COLLECTION
    return BookEntryKind.BOOK


def make_catalog_id(book: ParsedBook, seen: set[str]) -> str:
    """Create a readable stable id and disambiguate duplicate source rows."""
    base = normalize_title(book.search_title).replace(" ", "-") or "book"
    candidate = base
    suffix = 2
    while candidate in seen:
        candidate = f"{base}-{suffix}"
        suffix += 1
    seen.add(candidate)
    return candidate


def title_similarity(expected: str, actual: str) -> float:
    """Score title agreement while tolerating subtitles and series volumes."""
    expected_norm = normalize_title(expected)
    actual_norm = normalize_title(actual)
    if not expected_norm or not actual_norm:
        return 0.0
    if expected_norm == actual_norm:
        return 1.0
    expected_tokens = set(expected_norm.split())
    actual_tokens = set(actual_norm.split())
    overlap = len(expected_tokens & actual_tokens) / max(
        1, len(expected_tokens | actual_tokens)
    )
    containment = min(
        len(expected_tokens & actual_tokens) / len(expected_tokens),
        1.0,
    )
    sequence = SequenceMatcher(None, expected_norm, actual_norm).ratio()
    return max(sequence * 0.75 + overlap * 0.25, containment * 0.9)


def request_json(url: str, user_agent: str, timeout: float = 15.0) -> Any:
    """Read one JSON endpoint with an identifying user agent."""
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def search_google_books(title: str, user_agent: str) -> MetadataMatch | None:
    """Return the closest Google Books volume for a title."""
    params = urlencode(
        {
            "q": f'intitle:"{title}"',
            "printType": "books",
            "maxResults": 8,
        }
    )
    payload = request_json(
        f"https://www.googleapis.com/books/v1/volumes?{params}",
        user_agent,
    )
    matches: list[MetadataMatch] = []
    for item in payload.get("items", []):
        info = item.get("volumeInfo", {})
        actual_title = str(info.get("title", "")).strip()
        confidence = title_similarity(title, actual_title)
        if confidence <= 0:
            continue
        matches.append(
            MetadataMatch(
                source="google_books",
                title=actual_title,
                authors=tuple(str(value) for value in info.get("authors", [])),
                subjects=tuple(str(value) for value in info.get("categories", [])),
                description=str(info.get("description", "")),
                confidence=confidence,
            )
        )
    return max(matches, key=lambda match: match.confidence, default=None)


def search_open_library(title: str, user_agent: str) -> MetadataMatch | None:
    """Use Open Library only as a low-volume fallback for weak Google matches."""
    params = urlencode(
        {
            "title": title,
            "limit": 5,
            "fields": "title,author_name,subject",
        }
    )
    payload = request_json(
        f"https://openlibrary.org/search.json?{params}",
        user_agent,
    )
    matches: list[MetadataMatch] = []
    for item in payload.get("docs", []):
        actual_title = str(item.get("title", "")).strip()
        confidence = title_similarity(title, actual_title)
        if confidence <= 0:
            continue
        matches.append(
            MetadataMatch(
                source="open_library",
                title=actual_title,
                authors=tuple(
                    str(value) for value in item.get("author_name", [])[:3]
                ),
                subjects=tuple(str(value) for value in item.get("subject", [])[:80]),
                description="",
                confidence=confidence,
            )
        )
    return max(matches, key=lambda match: match.confidence, default=None)


def fetch_metadata(
    title: str,
    user_agent: str,
    *,
    google_enabled: bool = True,
    allow_open_library: bool = True,
) -> tuple[MetadataMatch | None, tuple[str, ...]]:
    """Search public metadata sources without turning failures into import errors."""
    warnings: list[str] = []
    google_match: MetadataMatch | None = None
    if google_enabled:
        try:
            google_match = search_google_books(title, user_agent)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            warnings.append(f"google_books_error:{type(exc).__name__}")
        if google_match and google_match.confidence >= 0.72:
            return google_match, tuple(warnings)
    if not allow_open_library:
        return google_match, tuple(warnings)

    try:
        open_library_match = search_open_library(title, user_agent)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        warnings.append(f"open_library_error:{type(exc).__name__}")
        return google_match, tuple(warnings)

    candidates = [match for match in (google_match, open_library_match) if match]
    return (
        max(candidates, key=lambda match: match.confidence, default=None),
        tuple(warnings),
    )


def tags_for(book: ParsedBook, metadata: MetadataMatch | None) -> tuple[str, ...]:
    """Map noisy metadata into at most four stable, searchable style tags."""
    normalized_title = normalize_title(book.search_title)
    override = TITLE_TAG_OVERRIDES.get(normalized_title, ())
    corpus_parts = [book.search_title, book.title_zh]
    if metadata and metadata.confidence >= 0.55:
        corpus_parts.extend(metadata.subjects)
        corpus_parts.append(metadata.description)
    corpus = " ".join(corpus_parts).casefold()

    found = set(override)
    for pattern, mapped_tags in TAG_RULES:
        if re.search(pattern, corpus, re.I):
            found.update(mapped_tags)
    found.intersection_update(STYLE_TAGS)

    if not found:
        if book.entry_kind in {BookEntryKind.BOOK, BookEntryKind.SERIES}:
            found.add("realistic_fiction")
        else:
            found.add("classic")
    ordered = list(override)
    ordered.extend(tag for tag in TAG_PRIORITY if tag in found and tag not in override)
    return tuple(ordered[:3])


def enrich_books(
    books: list[ParsedBook],
    *,
    offline: bool,
    user_agent: str,
    delay_seconds: float,
    workers: int,
    google_enabled: bool,
    allow_open_library: bool,
) -> tuple[list[BookCandidate], list[ImportRecord]]:
    """Enrich parsed rows, printing bounded progress for long network runs."""
    candidates: list[BookCandidate] = []
    records: list[ImportRecord] = []
    seen_ids: set[str] = set()
    total = len(books)
    lookup_results: dict[int, tuple[MetadataMatch | None, tuple[str, ...]]] = {}

    if not offline:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_index = {
                executor.submit(
                    fetch_metadata,
                    book.search_title,
                    user_agent,
                    google_enabled=google_enabled,
                    allow_open_library=allow_open_library,
                ): index
                for index, book in enumerate(books)
            }
            for completed, future in enumerate(as_completed(future_to_index), start=1):
                index = future_to_index[future]
                lookup_results[index] = future.result()
                if completed == total or completed % 10 == 0:
                    print(f"queried {completed}/{total}", flush=True)
                if delay_seconds > 0:
                    time.sleep(delay_seconds)

    for index, book in enumerate(books):
        warnings: list[str] = []
        metadata = None
        if not offline:
            metadata, metadata_warnings = lookup_results[index]
            warnings.extend(metadata_warnings)
            if metadata is None:
                warnings.append("no_metadata_match")
            elif metadata.confidence < 0.55:
                warnings.append("low_confidence_match")

        catalog_id = make_catalog_id(book, seen_ids)
        tags = tags_for(book, metadata)
        trusted_metadata = metadata if metadata and metadata.confidence >= 0.55 else None
        author = AUTHOR_OVERRIDES.get(normalize_title(book.search_title), "")
        if not author and trusted_metadata and trusted_metadata.authors:
            author = trusted_metadata.authors[0]
        candidate = BookCandidate(
            catalog_id=catalog_id,
            title_en=book.search_title,
            title_zh=book.title_zh,
            author=author,
            difficulty=BookDifficulty(
                book.difficulty_min,
                book.difficulty_max,
            ),
            entry_kind=book.entry_kind,
            genres=tags,
            raw_text=book.raw_text,
        )
        candidates.append(candidate)
        records.append(
            ImportRecord(
                catalog_id=catalog_id,
                source_index=book.source_index,
                search_title=book.search_title,
                matched_source=metadata.source if metadata else "",
                matched_title=metadata.title if metadata else "",
                match_confidence=round(metadata.confidence, 3) if metadata else 0.0,
                author=author,
                tags=tags,
                warnings=tuple(warnings),
            )
        )
    return candidates, records


def read_source(path: Path) -> list[ParsedBook]:
    """Read non-empty UTF-8 source rows and report invalid rows together."""
    books: list[ParsedBook] = []
    errors: list[str] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            books.append(parse_source_line(line, len(books) + 1))
        except ValueError as exc:
            errors.append(f"line {index}: {exc}")
    if errors:
        raise ValueError("\n".join(errors))
    return books


def import_catalog(database_path: Path, candidates: list[BookCandidate]) -> int:
    """Replace the local prototype catalog and close the database safely."""
    database = SQLiteDatabase(database_path)
    try:
        initialize_schema(database.connection)
        return SQLiteBookDifficultyCatalog(database).replace_all(candidates)
    finally:
        database.close()


def write_report(
    path: Path,
    source: Path,
    database: Path,
    records: list[ImportRecord],
) -> None:
    """Write a UTF-8 audit report outside the runtime catalog schema."""
    low_confidence = sum(
        "low_confidence_match" in record.warnings for record in records
    )
    unmatched = sum("no_metadata_match" in record.warnings for record in records)
    payload = {
        "source": str(source),
        "database": str(database),
        "record_count": len(records),
        "low_confidence_count": low_confidence,
        "unmatched_count": unmatched,
        "records": [asdict(record) for record in records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--database",
        type=Path,
        default=BACKEND_ROOT / "data" / "superhp.sqlite3",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=BACKEND_ROOT / "data" / "recommendation_import_report.json",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip public metadata calls and use title-based rules only.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds between completed lookups (default: 0).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Concurrent lookups; Open Library is capped at 3 (default: 3).",
    )
    parser.add_argument(
        "--provider",
        choices=("google-books", "open-library"),
        default="open-library",
        help="Primary public metadata source (default: open-library).",
    )
    parser.add_argument(
        "--open-library-fallback",
        action="store_true",
        help="Use Open Library for a small, manually selected source batch.",
    )
    parser.add_argument(
        "--user-agent",
        default="SuperHP-Agent-Catalog-Importer/0.1 (local educational project)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    books = read_source(args.source)
    open_library_enabled = (
        args.provider == "open-library" or args.open_library_fallback
    )
    worker_limit = 3 if open_library_enabled else 8
    candidates, records = enrich_books(
        books,
        offline=args.offline,
        user_agent=args.user_agent,
        delay_seconds=max(0.0, args.delay),
        workers=max(1, min(args.workers, worker_limit)),
        google_enabled=args.provider == "google-books",
        allow_open_library=open_library_enabled,
    )
    count = import_catalog(args.database, candidates)
    write_report(args.report, args.source, args.database, records)
    print(f"imported {count} catalog entries into {args.database}", flush=True)
    print(f"wrote audit report to {args.report}", flush=True)


if __name__ == "__main__":
    main()
