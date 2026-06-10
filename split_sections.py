"""Split HP chapters into sections at natural scene breaks."""
import re
from pathlib import Path

CORPUS = Path(r"D:\d_Software\codeTrain\superhp_Agent\corpus")


def split_chapter(ch_file):
    """Split one chapter file into sections at scene break markers."""
    content = ch_file.read_text(encoding="utf-8")

    # Parse frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    fm_text = parts[1].strip()
    body = parts[2].strip()

    # Extract metadata
    meta = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip('"')

    # Split body at scene breaks: literal "\*" on its own line
    sections = re.split(r"\n\\\*\n", body)
    sections = [s.strip() for s in sections if s.strip()]
    section_count = len(sections)

    if section_count == 0:
        return None

    return {
        "meta": meta,
        "sections": sections,
        "section_count": section_count,
    }


def write_sections(corpus_dir, ch_file, data):
    """Write split sections to hpXX/chYY/ directory."""
    meta = data["meta"]
    sections = data["sections"]
    book_id = meta.get("book_id", "hp00")
    chapter_no = int(meta.get("chapter_no", 0))
    chapter_title = meta.get("chapter_title", "")
    book_title = meta.get("book_title", "")
    summary = meta.get("summary", "")

    section_dir = corpus_dir / book_id / f"ch{chapter_no:02d}"
    section_dir.mkdir(parents=True, exist_ok=True)

    for i, sec_body in enumerate(sections, 1):
        sec_id = f"{book_id}-ch{chapter_no:02d}-sec{i:02d}"

        fm_lines = [
            f"id: {sec_id}",
            f"book_id: {book_id}",
            f'book_title: "{book_title}"',
            f"chapter_no: {chapter_no}",
            f'chapter_title: "{chapter_title}"',
            f"section_no: {i}",
            f"section_count: {len(sections)}",
        ]
        if summary:
            fm_lines.append(f'summary: "{summary}"')

        fm = "\n".join(fm_lines)
        content = f"---\n{fm}\n---\n\n{sec_body}\n"
        out_file = section_dir / f"{i:02d}.md"
        out_file.write_text(content, encoding="utf-8")

    return len(sections)


def main():
    books = sorted(
        d for d in CORPUS.iterdir()
        if d.is_dir() and d.name.startswith("hp")
    )

    total_chapters = 0
    total_sections = 0

    for book_dir in books:
        chapters = sorted(book_dir.glob("*.md"))
        bk_ch = 0
        bk_sec = 0

        for ch_file in chapters:
            data = split_chapter(ch_file)
            if not data:
                continue
            n = write_sections(CORPUS, ch_file, data)
            bk_ch += 1
            bk_sec += n

        if bk_ch > 0:
            print(f"{book_dir.name}: {bk_ch} chapters -> {bk_sec} sections ({bk_sec/bk_ch:.1f}/ch)")

        total_chapters += bk_ch
        total_sections += bk_sec

    print(f"\nTotal: {total_chapters} chapters -> {total_sections} sections")


if __name__ == "__main__":
    main()
