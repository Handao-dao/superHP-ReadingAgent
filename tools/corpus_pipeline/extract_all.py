"""Universal Harry Potter epub extractor — handles 3 different epub formats."""

import argparse
import re
import warnings
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from markdownify import markdownify as md

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EPUB_DIR = PROJECT_ROOT
DEFAULT_CORPUS_DIR = PROJECT_ROOT / "corpus"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-one": 21, "twenty-two": 22,
    "twenty-three": 23, "twenty-four": 24, "twenty-five": 25,
    "twenty-six": 26, "twenty-seven": 27, "twenty-eight": 28,
    "twenty-nine": 29, "thirty": 30, "thirty-one": 31, "thirty-two": 32,
    "thirty-three": 33, "thirty-four": 34, "thirty-five": 35,
    "thirty-six": 36, "thirty-seven": 37, "thirty-eight": 38,
}

TITLE_MAP = {
    "Philosopher": "01", "Chamber": "02", "Prisoner": "03",
    "Goblet": "04", "Order": "05", "Half-Blood": "06", "Deathly": "07",
}


def parse_toc_ncx(z, toc_path):
    """Parse NCX TOC: return {src_file: label_text} and {src_file: chapter_number}"""
    labels = {}
    with z.open(toc_path) as f:
        xml_str = f.read().decode("utf-8")
    root = ET.fromstring(xml_str)
    for nav in root.findall(f".//{{{NCX_NS}}}navPoint"):
        label = nav.find(f"{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text")
        src = nav.find(f"{{{NCX_NS}}}content")
        if label is not None and label.text and src is not None:
            src_val = src.get("src", "")
            labels[src_val] = label.text.strip()
    return labels


def detect_book_id(z, all_files):
    """Detect HP book number from OPF or filename patterns."""
    opf_path = None
    for f in all_files:
        if f.endswith(".opf"):
            opf_path = f
            break

    if opf_path:
        with z.open(opf_path) as f:
            opf_text = f.read().decode("utf-8")
        for key, bn in TITLE_MAP.items():
            if key in opf_text:
                return f"hp{bn}"

    # Fallback: scan filenames
    for f in all_files:
        m = re.search(r"hp(\d+)_ch", f)
        if m:
            return f"hp{int(m.group(1)):02d}"

    return "hp00"


def extract_chapter_title_from_html(soup):
    """Extract chapter title from various HTML formats."""
    # Format A: <span class="italic">Title</span> (hp01/02)
    spans = soup.find_all("span")
    for span in spans:
        if span.get("class") and any("italic" in str(c).lower() for c in span.get("class", [])):
            text = span.get_text(strip=True)
            if text and len(text) > 1:
                return text

    # Format B: <h3 class="chaptitle">Title</h3> (hp04)
    for tag in ["h3", "h2", "h1", "p"]:
        for el in soup.find_all(tag):
            cls = str(el.get("class", [])).lower()
            if "chaptitle" in cls or "chapter" in cls:
                text = el.get_text(strip=True)
                if text and len(text) > 1 and "chapter" not in text.lower():
                    return text

    # Format C: Title follows the CHAPTER heading in a <p> (hp03)
    h_tags = soup.find_all(["h1", "h2", "h3", "h4"])
    for h in h_tags:
        if h.get_text(strip=True).upper().startswith("CHAPTER"):
            # Next sibling with text
            for sibling in h.find_all_next(["p", "h3", "h2", "span", "div"], limit=5):
                text = sibling.get_text(strip=True)
                if text and len(text) > 1 and not text.upper().startswith("CHAPTER"):
                    return text

    return ""


def parse_epub(epub_file):
    chapters = {}
    with zipfile.ZipFile(epub_file) as z:
        all_files = z.namelist()
        book_id = detect_book_id(z, all_files)

        # Parse TOC
        toc_labels = {}
        for f in all_files:
            if f.endswith("toc.ncx"):
                toc_labels = parse_toc_ncx(z, f)
                break

        # Process each HTML file
        for f in sorted(all_files):
            if not f.endswith(".html") and not f.endswith(".xhtml"):
                continue
            info = z.getinfo(f)
            if info.file_size < 5000:
                continue
            if any(s in f.lower() for s in [
                "cover", "copyright", "dedication", "contents",
                "also_by", "experience", "pottermore", "template", "logo",
                "titlepage", "title_en", "title_page",
            ]):
                continue

            with z.open(f) as hf:
                raw = hf.read().decode("utf-8")

            # Find chapter number from heading or TOC
            ch_num = None

            # Method 1: HTML heading
            soup = BeautifulSoup(raw, "lxml")
            for tag in soup.find_all(["h1", "h2", "h3", "h4", "p"]):
                text = tag.get_text(strip=True)
                m = re.search(r"[–—]\s*CHAPTER\s+(\w+(?:[-\s]\w+)*)\s*[–—]", text, re.IGNORECASE)
                if m:
                    label = m.group(1).strip().lower()
                    ch_num = WORD_TO_NUM.get(label)
                    if ch_num is None and label.isdigit():
                        ch_num = int(label)
                    break

            # Method 2: TOC entry
            if ch_num is None:
                for src, label in toc_labels.items():
                    if f.endswith(src) or src.endswith(f.split("/")[-1]):
                        m = re.search(r"CHAPTER\s+(\w+(?:[-\s]\w+)*)", label, re.IGNORECASE)
                        if m:
                            lbl = m.group(1).strip().lower()
                            ch_num = WORD_TO_NUM.get(lbl)
                            if ch_num is None and lbl.isdigit():
                                ch_num = int(lbl)
                        break

            if ch_num is None:
                continue

            # Dedup: ignore hp05 preview chapters
            if book_id == "hp00":
                # Try to determine book from filename
                fm = re.search(r"hp(\d+)_ch", f)
                if fm:
                    file_book = f"hp{int(fm.group(1)):02d}"
                    if file_book != book_id and book_id != "hp00":
                        continue
                    book_id = file_book

            # Skip if this looks like a different book's chapter
            fm = re.search(r"hp(\d+)_ch", f)
            if fm:
                file_book = f"hp{int(fm.group(1)):02d}"
                if file_book != book_id:
                    continue

            # Extract title
            title = extract_chapter_title_from_html(soup)

            # Fallback: TOC subtitle entries
            if not title:
                for src, label in toc_labels.items():
                    if f.endswith(src.split("#")[0]) and "#" in src:
                        title = label
                        break

            if not title:
                continue

            # Read body
            body = soup.find("body")
            html_content = str(body) if body else raw

            if book_id not in chapters:
                chapters[book_id] = {}
            if ch_num not in chapters[book_id]:
                chapters[book_id][ch_num] = {
                    "number": ch_num, "title": title, "html": html_content,
                }

    # Convert to list format for downstream
    result = {}
    for bid, ch_dict in chapters.items():
        result[bid] = [ch_dict[k] for k in sorted(ch_dict.keys())]
    return result


def html_to_markdown(html_content):
    soup = BeautifulSoup(html_content, "lxml")
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()
    text = md(str(soup), heading_style="ATX", bullets="-", strip=["img", "svg"])
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def write_chapter(book_id, ch, book_title_map, *, corpus_dir, dry_run=False):
    book_dir = corpus_dir / book_id
    ch_no, ch_title = ch["number"], ch["title"]
    filename = f"{book_id}-ch{ch_no:02d}.md"
    filepath = book_dir / filename
    md_body = html_to_markdown(ch["html"])
    book_title = book_title_map.get(book_id, f"Harry Potter {book_id}")
    content = f"""---
id: {book_id}-ch{ch_no:02d}
book_id: {book_id}
book_title: "{book_title}"
chapter_no: {ch_no}
chapter_title: "{ch_title}"
---

{md_body}
"""
    if dry_run:
        print(f"  Would write: {filepath} ({len(md_body)} chars)")
        return
    book_dir.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    print(f"  Wrote: {filepath} ({len(md_body)} chars)")


BOOK_TITLES = {
    "hp01": "Harry Potter and the Philosopher's Stone",
    "hp02": "Harry Potter and the Chamber of Secrets",
    "hp03": "Harry Potter and the Prisoner of Azkaban",
    "hp04": "Harry Potter and the Goblet of Fire",
    "hp05": "Harry Potter and the Order of the Phoenix",
    "hp06": "Harry Potter and the Half-Blood Prince",
    "hp07": "Harry Potter and the Deathly Hallows",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epubs", nargs="*", type=Path, help="EPUB files to import")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help=f"output corpus directory (default: {DEFAULT_CORPUS_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse EPUB files and report outputs without writing corpus files",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    epubs = args.epubs or sorted(DEFAULT_EPUB_DIR.glob("*.epub"))

    if not epubs:
        raise SystemExit("No EPUB files found. Pass one or more EPUB paths explicitly.")

    for epub_file in epubs:
        if not epub_file.exists():
            print(f"Not found: {epub_file}")
            continue
        print(f"\n{'='*60}")
        print(f"Processing: {epub_file.name}")
        print(f"{'='*60}")
        chapters = parse_epub(epub_file)

        for book_id in sorted(chapters.keys()):
            book_chapters = sorted(chapters[book_id], key=lambda c: c["number"])
            book_title = BOOK_TITLES.get(book_id, f"Harry Potter {book_id}")
            print(f"\nBook: {book_title} ({len(book_chapters)} chapters)")
            for ch in book_chapters:
                write_chapter(
                    book_id,
                    ch,
                    BOOK_TITLES,
                    corpus_dir=args.corpus_dir.resolve(),
                    dry_run=args.dry_run,
                )

        print("\nSUMMARY")
        for book_id in sorted(chapters.keys()):
            count = len(chapters[book_id])
            print(f"  {book_id}: {count} chapters ({BOOK_TITLES.get(book_id, '?')})")
        print(f"  Total: {sum(len(c) for c in chapters.values())} chapters")


if __name__ == "__main__":
    main()
