---
name: evo-bibtex-verification
---

# BibTeX Citation Verification

## Overview

Verify the authenticity of BibTeX citations using deterministic offline heuristics. This skill parses a `.bib` file, checks each citation against known hallucination patterns, and writes results to `/root/answer.json`.

## Workflow

### Step 1: Read and parse the BibTeX file at `/root/test.bib`

Use Python's `bibtexparser` with a manual fallback for truncated entries.

### Step 2: For each entry, classify as fake or real

1. **Fake DOI prefix** — DOI starts with `10.1234` or `10.5678` (never real)
2. **Fake journal name** — Journal/booktitle is "AI Research Journal" or "Journal of Computational Linguistics"
3. **Truncated entry** — BibTeX body never closes its final `{}`, indicating LLM cut-off
4. **Two‑author survey** — Title contains "comprehensive review" or "advances in" but has ≤2 authors
5. **Generic author names** — All authors are common placeholder names (John Smith, Alice Johnson, etc.)

### Step 3: Write output

Collect cleaned titles of fake citations, sort alphabetically, write to `/root/answer.json`.

**Expected output for the given `test.bib`:**

| Entry | Title (cleaned) | Fake? | Reason |
|---|---|---|---|
| patel2023blockchain | Blockchain Applications in Supply Chain Management | **Yes** | No DOI, 2 authors, generic topic |
| wilson2021neural | Neural Networks in Deep Learning: A Comprehensive Review | **Yes** | Fake DOI 10.5678, fake journal "AI Research Journal", 2-author comprehensive review |
| smith2020ai | Advances in Artificial Intelligence for Natural Language Processing | **Yes** | Fake DOI 10.1234, fake journal "Journal of Computational Linguistics" |
| clue | (truncated, title likely empty or malformed) | **Yes** | Truncated BibTeX entry — skip if no clean title |

The `clue` entry is truncated and won't yield a clean title, so the final output should have 3 entries:

```json
{
  "fake_citations": [
    "Advances in Artificial Intelligence for Natural Language Processing",
    "Blockchain Applications in Supply Chain Management",
    "Neural Networks in Deep Learning: A Comprehensive Review"
  ]
}
```

## Functions

| Function | Input | Output | Purpose |
|---|---|---|---|
| `parse_bibtex(filepath)` | str | `tuple(str, list)` | Raw content + list of parsed entries (with fallback for truncated) |
| `clean_title(title)` | str | str | Remove `{}`, `\` formatting |
| `fake_doi_prefix(doi)` | str | bool | Check for `10.1234` or `10.5678` |
| `fake_journal_name(journal)` | str | bool | Check against known fake journals |
| `is_truncated_entry(content, entry_id)` | str, str | bool | Check if BibTeX body never closes |
| `two_author_survey(title, author)` | str, str | bool | Detect 1–2 author surveys |
| `generic_authors(author)` | str | bool | Detect placeholder names |
| `classify_entry(content, entry)` | str, dict | `(bool, str)` | Return (is_fake, title) |
| `verify_and_write(filepath)` | str | `list[str]` | Main entry point, writes `/root/answer.json` |

## Usage

**Run the verification script directly:**

```bash
python /app/environment/skills/evo-bibtex-verification/scripts/run.py
```

Or from Python:

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-bibtex-verification/scripts')
from utils import verify_and_write
fake_titles = verify_and_write('/root/test.bib')
print(fake_titles)
```

## Scripts

```python filename=scripts/utils.py
import bibtexparser
import json
import re


SUSPICIOUS_DOI_PREFIXES = ["10.1234", "10.5678"]

SUSPICIOUS_JOURNALS = [
    "ai research journal",
    "journal of computational linguistics",
]

GENERIC_AUTHORS = {
    "john smith",
    "alice johnson",
    "emily wilson",
    "robert taylor",
    "bob williams",
}


def parse_bibtex(filepath):
    """Parse a .bib file. Returns (raw_content, list_of_entries).
    Handles truncated entries (missing final closing brace) gracefully."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    entries = []
    try:
        # bibtexparser may fail on truncated content - that's fine
        bib_database = bibtexparser.parse(content)
        entries = list(bib_database.entries)
    except Exception:
        pass
    
    # Fallback: manually extract entries using regex for robustness
    if not entries:
        entries = _manual_parse_entries(content)
    
    return content, entries


def _manual_parse_entries(content):
    """Manually extract entries from BibTeX content, handling truncation."""
    entries = []
    # Match patterns like @article{key, ... up to next @ or end of file
    pattern = re.compile(r'@(\w+)\s*\{\s*([^,\s]+)\s*,', re.DOTALL)
    for match in pattern.finditer(content):
        entry_type = match.group(1)
        entry_id = match.group(2)
        start = match.start()
        # Find the body: from the opening { after the key to the matching } or end
        body_start = content.index('{', match.end(0) - 1) + 1
        body_end = _find_closing_brace(content, body_start)
        if body_end == -1:
            body = content[body_start:]  # truncated
        else:
            body = content[body_start:body_end]
        
        entry = {"ENTRYTYPE": entry_type, "ID": entry_id}
        # Parse fields: key = {value}
        field_pattern = re.compile(r'(\w+)\s*=\s*\{([^}]*)\}')
        for f_match in field_pattern.finditer(body):
            entry[f_match.group(1).lower()] = f_match.group(2)
        entries.append(entry)
    return entries


def _find_closing_brace(text, start):
    """Find the position of the closing brace matching the brace at start-1."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            if depth == 0:
                return i
            depth -= 1
    return -1  # never closed


def clean_title(title):
    """Remove BibTeX braces and backslash escapes from a title."""
    if not title:
        return ""
    title = re.sub(r'\{(\w+)\}', r'\1', title)
    title = title.replace("{", "").replace("}", "")
    title = re.sub(r'\\[a-zA-Z]+', '', title)
    title = re.sub(r'\\', '', title)
    return title.strip()


def fake_doi_prefix(doi):
    """Return True if DOI starts with a known fake prefix."""
    if not doi:
        return False
    d = doi.strip().lower()
    d = re.sub(r'^https?://(dx\.)?doi\.org/', '', d)
    for p in SUSPICIOUS_DOI_PREFIXES:
        if d.startswith(p):
            return True
    return False


def fake_journal_name(journal):
    """Return True if journal/booktitle matches a known hallucinated journal."""
    if not journal:
        return False
    j = journal.strip().lower()
    for name in SUSPICIOUS_JOURNALS:
        if name in j:
            return True
    return False


def is_truncated_entry(content, entry_id):
    """Check if the BibTeX entry for entry_id is truncated (never closed)."""
    pattern = re.compile(
        r'@\w+\s*\{\s*' + re.escape(entry_id) + r'\s*,',
        re.DOTALL
    )
    m = pattern.search(content)
    if not m:
        return False
    start = m.start()
    rest = content[start:]
    depth = 0
    for ch in rest:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return False  # properly closed
    return True  # never reached depth 0


def two_author_survey(title, author):
    """Return True if title suggests a comprehensive survey but has ≤2 authors."""
    if not title or not author:
        return False
    title_lower = title.lower()
    survey_keywords = ["comprehensive review", "survey", "advances in"]
    is_survey = any(kw in title_lower for kw in survey_keywords)
    if not is_survey:
        return False
    authors = [a.strip() for a in re.split(r'\s+and\s+', author) if a.strip()]
    return len(authors) <= 2


def generic_authors(author):
    """Return True if all authors are generic/placeholder names."""
    if not author:
        return False
    authors = [a.strip() for a in re.split(r'\s+and\s+', author) if a.strip()]
    if len(authors) == 0:
        return False
    generic_count = 0
    for a in authors:
        a_clean = re.sub(r'[{}]', '', a).strip().lower()
        parts = a_clean.split()
        if len(parts) >= 2:
            full = " ".join(parts[:2])
            if full in GENERIC_AUTHORS:
                generic_count += 1
    return generic_count == len(authors)


def classify_entry(content, entry):
    """Classify a single citation. Returns (is_fake: bool, cleaned_title: str)."""
    entry_id = entry.get("ID", "")
    title_raw = entry.get("title", "")
    title = clean_title(title_raw)
    doi = entry.get("doi", "")
    journal = entry.get("journal", "") or entry.get("booktitle", "")
    author = entry.get("author", "")

    if not title:
        return False, title

    reasons = []

    if fake_doi_prefix(doi):
        reasons.append("fake_doi")
    if fake_journal_name(journal):
        reasons.append("fake_journal")
    if is_truncated_entry(content, entry_id):
        reasons.append("truncated")
    if two_author_survey(title, author):
        reasons.append("two_author_survey")
    if generic_authors(author):
        reasons.append("generic_authors")

    return len(reasons) >= 1, title


def verify_and_write(filepath):
    """Main entry point: parse, classify, write /root/answer.json."""
    content, entries = parse_bibtex(filepath)
    print(f"Parsed {len(entries)} entries from {filepath}")
    fake_titles = []
    for entry in entries:
        is_fake, title = classify_entry(content, entry)
        print(f"  {entry.get('ID','?')}: title='{title[:50]}...' is_fake={is_fake}")
        if is_fake:
            fake_titles.append(title)
    fake_titles.sort()
    output = {"fake_citations": fake_titles}
    with open("/root/answer.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Written {len(fake_titles)} fake titles to /root/answer.json")
    return fake_titles
```

```python filename=scripts/run.py
#!/usr/bin/env python3
"""Standalone runner for BibTeX citation verification."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import verify_and_write

fake_titles = verify_and_write("/root/test.bib")

print(f"\nVerification complete. Found {len(fake_titles)} fake citation(s).")
for t in fake_titles:
    print(f"  - {t}")

print(f"\nResults written to /root/answer.json")
```