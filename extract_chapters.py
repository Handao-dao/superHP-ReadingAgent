"""Extract Harry Potter epub chapters into structured Markdown corpus."""
import zipfile
import xml.etree.ElementTree as ET
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as md

EPUB_PATH = Path(r"D:\d_Software\codeTrain\superhp_Agent")
CORPUS = EPUB_PATH / "corpus"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"


def parse_epub(epub_file):
    """Parse epub and return chapters grouped by book."""
    chapters = {}  # book_id -> list of {number, title, html_content}

    with zipfile.ZipFile(epub_file) as z:
        # Parse TOC for chapter titles
        toc_chapters = []
        if "OEBPS/toc.ncx" in z.namelist():
            with z.open("OEBPS/toc.ncx") as f:
                toc_xml = f.read().decode("utf-8")
            root = ET.fromstring(toc_xml)
            for nav in root.findall(f".//{{{NCX_NS}}}navPoint"):
                label = nav.find(f"{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text")
                src = nav.find(f"{{{NCX_NS}}}content")
                if label is not None and src is not None:
                    toc_chapters.append({
                        "label": label.text.strip() if label.text else "",
                        "src": src.get("src", ""),
                    })

        # Parse each chapter HTML
        for entry in toc_chapters:
            label = entry["label"]
            src = entry["src"]

            # Match "Chapter X - Title"
            m = re.match(r"Chapter\s+(\d+)\s*[-–—]\s*(.+)", label)
            if not m:
                continue

            chapter_no = int(m.group(1))
            chapter_title = m.group(2).strip()

            # Determine book from filename pattern
            file_match = re.match(r"hp(\d+)_ch(\d+)_", src)
            if not file_match:
                continue
            book_no = int(file_match.group(1))
            book_id = f"hp{book_no:02d}"

            # Read and convert chapter HTML (TOC src lacks OEBPS/ prefix)
            html_path = f"OEBPS/{src}"
            html_content = ""
            if html_path in z.namelist():
                with z.open(html_path) as f:
                    raw = f.read().decode("utf-8")
                soup = BeautifulSoup(raw, "lxml")
                body = soup.find("body")
                if body:
                    html_content = str(body)
                else:
                    html_content = raw

            if book_id not in chapters:
                chapters[book_id] = []
            chapters[book_id].append({
                "number": chapter_no,
                "title": chapter_title,
                "html": html_content,
            })

    return chapters


def html_to_markdown(html_content):
    """Convert chapter HTML body to clean Markdown."""
    soup = BeautifulSoup(html_content, "lxml")

    # Remove script, style, head tags
    for tag in soup(["script", "style", "head", "meta", "link"]):
        tag.decompose()

    # Convert to markdown
    text = md(
        str(soup),
        heading_style="ATX",
        bullets="-",
        strip=["img", "svg"],
    )

    # Clean up excess whitespace
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = text.strip()

    return text


def write_chapter(book_id, ch, book_title_map):
    """Write a single chapter as Markdown file."""
    book_dir = CORPUS / book_id
    book_dir.mkdir(parents=True, exist_ok=True)

    ch_no = ch["number"]
    ch_title = ch["title"]
    filename = f"{book_id}-ch{ch_no:02d}.md"
    filepath = book_dir / filename

    markdown_body = html_to_markdown(ch["html"])
    book_title = book_title_map.get(book_id, f"Harry Potter {book_id}")

    # YAML frontmatter
    content = f"""---
id: {book_id}-ch{ch_no:02d}
book_id: {book_id}
book_title: "{book_title}"
chapter_no: {ch_no}
chapter_title: "{ch_title}"
---

{markdown_body}
"""
    filepath.write_text(content, encoding="utf-8")
    print(f"  Wrote: {filepath} ({len(markdown_body)} chars)")


def main():
    BOOK_TITLES = {
        "hp01": "Harry Potter and the Philosopher's Stone",
        "hp02": "Harry Potter and the Chamber of Secrets",
        "hp03": "Harry Potter and the Prisoner of Azkaban",
        "hp04": "Harry Potter and the Goblet of Fire",
        "hp05": "Harry Potter and the Order of the Phoenix",
        "hp06": "Harry Potter and the Half-Blood Prince",
        "hp07": "Harry Potter and the Deathly Hallows",
    }

    # Accept specific epub via command line, or process all
    if len(sys.argv) > 1:
        epubs = [Path(p) for p in sys.argv[1:]]
    else:
        epubs = sorted(EPUB_PATH.glob("*.epub"))

    if not epubs:
        print("No epub file found!")
        sys.exit(1)

    for epub_file in epubs:
        if not epub_file.exists():
            print(f"File not found: {epub_file}")
            continue
        print(f"Processing: {epub_file.name}")
        chapters = parse_epub(epub_file)

        for book_id in sorted(chapters.keys()):
            book_chapters = sorted(chapters[book_id], key=lambda c: c["number"])
            book_title = BOOK_TITLES.get(book_id, f"Harry Potter {book_id}")
            print(f"\nBook: {book_title} ({len(book_chapters)} chapters)")

            for ch in book_chapters:
                write_chapter(book_id, ch, BOOK_TITLES)

        # Print summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        for book_id in sorted(chapters.keys()):
            count = len(chapters[book_id])
            print(f"  {book_id}: {count} chapters")
        print(f"  Total: {sum(len(c) for c in chapters.values())} chapters")
        print("=" * 60)


if __name__ == "__main__":
    main()
