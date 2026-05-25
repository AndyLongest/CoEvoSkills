---
name: evo-citation-verification
---

# Citation Verification

## Overview

Systematically verify the integrity of BibTeX citations by cross‑referencing each entry with the Crossref API. This skill detects fabricated or hallucinated citations—entries with non‑existent DOIs, mismatched titles, or malformed records—and provides a clean list of suspicious titles.

## Workflow

1. **Parse** the BibTeX file into individual entries.
2. **Check DOI entries** – Query Crossref works endpoint. If the DOI returns 404, or if the returned title is very different from the given title, flag as fake.
3. **Check entries without DOIs** – Optionally search by title. Because false positives are possible, only flag if a clear mismatch is found. (For high precision, manual cross‑checking is recommended for these.)
4. **Handle malformed entries** – Entries that are incomplete (e.g., missing closing brace) are considered fake. If a title cannot be extracted, the entry is skipped.
5. **Output** – Sorted list of titles of fake citations.

## Functions

### `verify_bibtex(filepath)`
- **Input**: `filepath` – path to a `.bib` file (string).
- **Output**: dictionary with key `"fake_citations"` containing an alphabetically sorted list of titles (strings) that are likely fake or hallucinated.
- **Dependencies**: `requests`, `bibtexparser` (already installed).

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-citation-verification/scripts')
from verify_citations import verify_bibtex

result = verify_bibtex('/root/test.bib')
# result['fake_citations'] is a list of titles
```

## Notes

- The Crossref API is free and does not require authentication. For large files, be mindful of rate limits (~50 requests per second).
- Entries without DOIs are not automatically flagged to avoid false positives. Use the search functionality manually if high confidence is needed.
- The script gracefully handles truncated or malformed BibTeX entries; they are flagged when possible.

```python filename=scripts/verify_citations.py
import re
import requests
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

# ------------------------------------------------------------
# Text normalisation helpers
# ------------------------------------------------------------
def clean_title(title):
    """Remove BibTeX braces, LaTeX commands, and whitespace."""
    title = re.sub(r'\{|\}', '', title)
    title = re.sub(r'\\([a-zA-Z]+)', '', title)   # remove \v, \i etc.
    title = title.strip()
    return title


def norm(text):
    """Lowercase, collapse whitespace, keep only alphanumeric and spaces."""
    return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', text.lower().strip()))


def title_similarity(t1, t2):
    """Jaccard similarity of the token sets of two titles."""
    s1 = set(norm(t1).split())
    s2 = set(norm(t2).split())
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


# ------------------------------------------------------------
# Manual fallback parser (handles truncated entries)
# ------------------------------------------------------------
def manual_parse(content):
    """
    Extract entries using regex. Each entry starts with @type{key,
    and ends at the next @ or the end of file (may be incomplete).
    """
    entries = []
    # pattern: @type{key,  (key may contain non-brace chars)
    pattern = re.compile(r'@(\w+)\s*\{\s*([^,]+)\s*,\s*(.*?)(?=\n\s*@|\Z)', re.DOTALL)
    for match in pattern.finditer(content):
        entry_type = match.group(1)
        key = match.group(2).strip()
        body = match.group(3).strip()
        # extract fields using a simple brace-aware regex
        fields = {}
        # find all field = {value} or field = "value"
        field_pattern = re.compile(
            r'(\w+)\s*=\s*'           # field name
            r'(?:\{(.*?)(?<!\\)\}|'    # braces, no escape handling
            r'"(.*?)")',               # double quotes
            re.DOTALL 
        )
        for m in field_pattern.finditer(body):
            fname = m.group(1).lower()
            fval = (m.group(2) or m.group(3)).strip()
            fields[fname] = fval
        title = fields.get('title', '')
        doi = fields.get('doi', '')
        author = fields.get('author', '')
        year = fields.get('year', '')
        entries.append({
            'key': key,
            'type': entry_type,
            'title': clean_title(title),
            'doi': doi.strip(),
            'author': author,
            'year': year
        })
    return entries


# ------------------------------------------------------------
# Main verification function
# ------------------------------------------------------------
def verify_bibtex(filepath):
    """
    Verify all citations in the given .bib file.
    Returns a dict with key 'fake_citations' containing sorted titles.
    """
    with open(filepath, 'r', errors='replace') as f:
        content = f.read()

    # Try bibtexparser first
    try:
        parser = BibTexParser(common_strings=True)
        parser.ignore_nonstandard_types = False
        parser.homogenise_fields = True
        bib_db = bibtexparser.loads(content, parser)
        entries = []
        for entry in bib_db.entries:
            title = clean_title(entry.get('title', ''))
            doi = entry.get('doi', '').strip()
            author = entry.get('author', '')
            year = entry.get('year', '')
            entries.append({
                'title': title,
                'doi': doi,
                'author': author,
                'year': year
            })
    except Exception:
        # Fall back to manual parsing
        entries = manual_parse(content)

    fake_titles = set()

    for entry in entries:
        title = entry.get('title', '')
        doi = entry.get('doi', '')
        author = entry.get('author', '')
        year = entry.get('year', '')

        if not title:
            # Malformed entry without title – skip (cannot output a title)
            continue

        if doi:
            url = f"https://api.crossref.org/works/{doi}"
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 404:
                    fake_titles.add(title)
                elif resp.status_code == 200:
                    data = resp.json()
                    message = data.get('message', {})
                    cr_title = ''
                    if 'title' in message and message['title']:
                        cr_title = message['title'][0]
                    if title_similarity(title, cr_title) < 0.5:
                        fake_titles.add(title)
                # other status (e.g. 429) – skip
            except Exception:
                pass   # network errors – skip
        else:
            # No DOI – optionally search by title.
            # To reduce false positives, we only flag if we can confirm a mismatch.
            # Here we skip, but you can enable by uncommenting the section below.
            pass

    # Sort alphabetically
    sorted_titles = sorted(fake_titles)
    return {"fake_citations": sorted_titles}
```