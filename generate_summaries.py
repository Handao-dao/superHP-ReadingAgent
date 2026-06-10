"""Generate English summaries for hp01 chapters using Proma Cloud API."""
import os
import re, json, sys, time
from pathlib import Path
import urllib.request

API_KEY = os.getenv("PROMA_API_KEY", "")
BASE_URL = "https://api.proma.cool/api/v1"
CORPUS = Path(r"D:\d_Software\codeTrain\superhp_Agent\corpus\hp01")

SYSTEM_PROMPT = """You are a literary summarizer. Read the provided chapter excerpt from Harry Potter and the Philosopher's Stone and write a concise 2-3 sentence summary in English.

Guidelines:
- Capture the key events and developments in this chapter
- Use present tense
- Keep to 2-3 sentences, plain English, no markdown
- Focus on what happens, not thematic analysis

Return ONLY the summary text, nothing else."""


def extract_excerpt(text, max_chars=4000):
    """Extract beginning + middle + end of chapter for balanced context."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    third = max_chars // 3
    start = text[:third]
    mid_start = len(text) // 2 - third // 2
    middle = text[mid_start:mid_start + third]
    end = text[-third:]
    return f"{start}\n\n[...]\n\n{middle}\n\n[...]\n\n{end}"


def call_api(excerpt):
    """Call Proma Cloud API for summary."""
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Chapter excerpt:\n\n{excerpt}"}
        ],
        "max_tokens": 200,
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"].strip()


def update_chapter(filepath):
    """Read chapter, generate summary, update frontmatter."""
    content = filepath.read_text(encoding="utf-8")

    # Extract body text (without frontmatter)
    parts = content.split("---", 2)
    if len(parts) < 3:
        print(f"  SKIP {filepath.name}: no valid frontmatter")
        return

    frontmatter = parts[1].strip()
    body = parts[2].strip()

    # Skip if summary already exists
    if re.search(r"^summary:", frontmatter, re.MULTILINE):
        print(f"  SKIP {filepath.name}: summary already exists")
        return

    # Generate summary from excerpt
    excerpt = extract_excerpt(body)
    try:
        summary = call_api(excerpt)
    except Exception as e:
        print(f"  ERROR {filepath.name}: {e}")
        return

    # Insert summary line before the closing --- of frontmatter
    new_frontmatter = frontmatter.rstrip() + f"\nsummary: \"{summary}\"\n"

    # Rebuild file
    new_content = f"---\n{new_frontmatter}---\n\n{body}"
    filepath.write_text(new_content, encoding="utf-8")
    print(f"  OK {filepath.name}: {summary[:80]}...")


def main():
    chapters = sorted(CORPUS.glob("hp01-ch*.md"))
    print(f"Processing {len(chapters)} chapters...\n")

    for i, ch in enumerate(chapters):
        print(f"[{i+1}/{len(chapters)}] {ch.name}")
        update_chapter(ch)
        if i < len(chapters) - 1:
            time.sleep(0.5)  # Rate limit courtesy

    print("\nDone.")


if __name__ == "__main__":
    main()
