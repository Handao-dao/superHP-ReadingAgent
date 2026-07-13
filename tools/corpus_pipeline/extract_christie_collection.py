"""Extract selected Agatha Christie novels from the inspected collection EPUB.

The source collection mixes several EPUB layouts and contains non-novel front
matter copied from reference sites.  This importer deliberately selects only
the chapter files for the eight reviewed novels and writes the same one-book /
one-chapter Markdown layout used by the Harry Potter corpus.
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from markdownify import markdownify as md


warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = PROJECT_ROOT / "corpus"
TEXT_ROOT = "OEBPS/Text"

NUMBER_WORDS = {
    1: "One",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
    11: "Eleven",
    12: "Twelve",
    13: "Thirteen",
    14: "Fourteen",
    15: "Fifteen",
    16: "Sixteen",
    17: "Seventeen",
    18: "Eighteen",
    19: "Nineteen",
    20: "Twenty",
    21: "Twenty-one",
    22: "Twenty-two",
    23: "Twenty-three",
    24: "Twenty-four",
    25: "Twenty-five",
    26: "Twenty-six",
    27: "Twenty-seven",
    28: "Twenty-eight",
    29: "Twenty-nine",
    30: "Thirty",
    31: "Thirty-one",
    32: "Thirty-two",
}


@dataclass(frozen=True)
class SourceChapter:
    filename: str
    part: str = ""
    part_chapter_no: int | None = None
    title_override: str = ""


@dataclass(frozen=True)
class BookSpec:
    book_id: str
    title: str
    chapters: tuple[SourceChapter, ...]


def numbered_files(prefix: str, start: int, end: int, extension: str, *, part: str = ""):
    return tuple(
        SourceChapter(
            filename=f"{prefix}-{number:02d}.{extension}",
            part=part,
            part_chapter_no=(number - start + 1) if part else None,
        )
        for number in range(start, end + 1)
    )


BOOKS = (
    BookSpec(
        "ac01",
        "And Then There Were None",
        numbered_files("AndThenThereWereNone", 7, 22, "html")
        + (
            SourceChapter("AndThenThereWereNone-23.html", title_override="Epilogue"),
            SourceChapter(
                "AndThenThereWereNone-24.html",
                title_override=(
                    "A Manuscript Document Sent to Scotland Yard by the Master "
                    "of the Emma Jane Fishing Trawler"
                ),
            ),
        ),
    ),
    BookSpec(
        "ac02",
        "Murder on the Orient Express",
        numbered_files("orient", 5, 12, "xhtml", part="Part I")
        + numbered_files("orient", 14, 28, "xhtml", part="Part II")
        + numbered_files("orient", 31, 39, "xhtml", part="Part III"),
    ),
    BookSpec(
        "ac03",
        "The Murder of Roger Ackroyd",
        numbered_files("ackroyd", 8, 34, "xhtml"),
    ),
    BookSpec(
        "ac04",
        "Death on the Nile",
        numbered_files("nile", 5, 35, "html"),
    ),
    BookSpec(
        "ac05",
        "A Murder Is Announced",
        numbered_files("announced", 6, 28, "xhtml")
        + (SourceChapter("announced-29.xhtml", title_override="Epilogue"),),
    ),
    BookSpec(
        "ac06",
        "Five Little Pigs",
        numbered_files("pigs", 7, 16, "html", part="Book One")
        + numbered_files("pigs", 18, 22, "html", part="Book Two")
        + numbered_files("pigs", 24, 28, "html", part="Book Three"),
    ),
    BookSpec(
        "ac07",
        "Crooked House",
        numbered_files("crooked", 6, 31, "html"),
    ),
    BookSpec(
        "ac08",
        "Endless Night",
        numbered_files("endless", 6, 13, "xhtml", part="Book One")
        + numbered_files("endless", 15, 24, "xhtml", part="Book Two")
        + numbered_files("endless", 26, 31, "xhtml", part="Book Three"),
    ),
)


def clean_text(value: str) -> str:
    """Normalize invisible EPUB layout characters without rewriting prose."""
    return " ".join(value.replace("\u00ad", "").replace("\ufeff", "").split())


def visible_blocks(soup: BeautifulSoup) -> list[str]:
    body = soup.find("body") or soup
    blocks = []
    for tag in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
        text = clean_text(tag.get_text(" ", strip=True))
        if text:
            blocks.append(text)
    return blocks


def source_heading(soup: BeautifulSoup) -> str:
    body = soup.find("body") or soup
    heading = body.find(["h1", "h2", "h3", "h4", "h5", "h6"])
    return clean_text(heading.get_text(" ", strip=True)) if heading else ""


def title_from_source(spec: BookSpec, source: SourceChapter, soup: BeautifulSoup, index: int) -> str:
    if source.title_override:
        return source.title_override

    blocks = visible_blocks(soup)
    heading = source_heading(soup)

    if spec.book_id in {"ac02", "ac03"}:
        # These editions put the number in a heading and the real title in the
        # following paragraph.
        subtitle = next((item for item in blocks if item != heading), "")
        if subtitle:
            if source.part:
                return f"{source.part} — {subtitle.title()}"
            return subtitle.title()

    if spec.book_id == "ac05":
        # Example: "Twenty-one THREE WOMEN".
        label = heading
        label = re.sub(r"^[A-Za-z-]+\s+", "", label, count=1).strip()
        if label:
            return label.title()

    if spec.book_id == "ac06":
        label = heading
        label = re.sub(r"^[A-Za-z-]+\s+", "", label, count=1).strip()
        label = label.replace("Counsel fot the Defence", "Counsel for the Defence")
        label = label.replace("This little had roast beef", "This little pig had roast beef")
        if source.part == "Book Two" and heading.startswith("Narrative of"):
            label = heading
        if label:
            return f"{source.part} — {label}"

    chapter_label = NUMBER_WORDS.get(index, str(index))
    if source.part:
        part_no = source.part_chapter_no or index
        return f"{source.part} — Chapter {NUMBER_WORDS.get(part_no, part_no)}"
    return f"Chapter {chapter_label}"


def html_to_markdown(raw: bytes) -> tuple[BeautifulSoup, str]:
    html = raw.decode("utf-8").replace("\u00ad", "").replace("\ufeff", "")
    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body") or soup
    for tag in body.find_all(["script", "style", "head", "meta", "link", "img", "svg"]):
        tag.decompose()
    text = md(str(body), heading_style="ATX", bullets="-", strip=["img", "svg"])
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return soup, text.strip()


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_markdown(spec: BookSpec, chapter_no: int, chapter_title: str, body: str) -> str:
    unit_id = f"{spec.book_id}-ch{chapter_no:02d}"
    return f"""---
id: {unit_id}
chapter_id: {unit_id}
book_id: {spec.book_id}
book_title: {yaml_string(spec.title)}
chapter_no: {chapter_no}
chapter_title: {yaml_string(chapter_title)}
summary: ""
---

{body}
"""


def import_book(
    archive: zipfile.ZipFile,
    spec: BookSpec,
    corpus_dir: Path,
    *,
    dry_run: bool,
    force: bool,
) -> tuple[int, int]:
    target_dir = corpus_dir / spec.book_id
    existing = list(target_dir.glob("*.md")) if target_dir.exists() else []
    if existing and not force and not dry_run:
        raise SystemExit(
            f"Refusing to overwrite {target_dir}; pass --force to replace existing chapter files."
        )

    names = set(archive.namelist())
    missing = [
        f"{TEXT_ROOT}/{chapter.filename}"
        for chapter in spec.chapters
        if f"{TEXT_ROOT}/{chapter.filename}" not in names
    ]
    if missing:
        raise SystemExit(f"Missing source files for {spec.book_id}: {missing}")

    total_chars = 0
    outputs: list[tuple[Path, str]] = []
    for chapter_no, source in enumerate(spec.chapters, start=1):
        archive_path = f"{TEXT_ROOT}/{source.filename}"
        soup, body = html_to_markdown(archive.read(archive_path))
        if len(body) < 500:
            raise SystemExit(f"Chapter body is unexpectedly short: {archive_path} ({len(body)} chars)")
        chapter_title = title_from_source(spec, source, soup, chapter_no)
        output_path = target_dir / f"{spec.book_id}-ch{chapter_no:02d}.md"
        outputs.append((output_path, render_markdown(spec, chapter_no, chapter_title, body)))
        total_chars += len(body)

    print(f"{spec.book_id}: {spec.title} — {len(outputs)} units, {total_chars:,} chars")
    if dry_run:
        for path, content in outputs:
            print(f"  Would write {path.name} ({len(content):,} chars)")
        return len(outputs), total_chars

    target_dir.mkdir(parents=True, exist_ok=True)
    if force:
        for path in existing:
            path.unlink()
    for path, content in outputs:
        path.write_text(content, encoding="utf-8", newline="\n")
    return len(outputs), total_chars


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path, help="Agatha Christie collection EPUB")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    epub = args.epub.expanduser().resolve()
    corpus_dir = args.corpus_dir.expanduser().resolve()
    if not epub.is_file():
        raise SystemExit(f"EPUB not found: {epub}")

    total_units = 0
    total_chars = 0
    with zipfile.ZipFile(epub) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise SystemExit(f"EPUB CRC failure: {bad_member}")
        for spec in BOOKS:
            units, chars = import_book(
                archive,
                spec,
                corpus_dir,
                dry_run=args.dry_run,
                force=args.force,
            )
            total_units += units
            total_chars += chars
    print(f"Total: {total_units} units, {total_chars:,} chars")


if __name__ == "__main__":
    main()
