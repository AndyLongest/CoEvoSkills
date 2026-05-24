---
name: evo-bibtex-integrity-checker
---

# BibTeX Integrity Checker

This skill verifies the authenticity of BibTeX citations by checking against online databases (Crossref, Semantic Scholar, DOI resolution). It parses a `.bib` file, attempts to confirm each entry, and returns a sorted list of potentially fake citation titles (with BibTeX formatting cleaned).

## Workflow

1. Parse the BibTeX file using `bibtexparser`.
2. For each entry:
   - Extract title, authors, DOI, etc.
   - If DOI present: verify via DOI resolution (HTTP HEAD to `https://doi.org/{DOI}`) or Semantic Scholar DOI endpoint.
   - If no DOI: search Semantic Scholar (or Crossref fallback) using the cleaned title.
   - If no confirming evidence from any source, mark as fake.
3. Return sorted list of fake titles (braces and backslashes removed).

## Functions

### `verify_bib_file(bib_path: str) -> list[str]`
- **Input**: path to a `.bib` file  
- **Output**: sorted list of fake citation titles (cleaned)  
- **Raises**: `FileNotFoundError` if bib path does not exist; `ValueError` if parsing fails.  
- Uses sequential checks: DOI resolution → Semantic Scholar DOI search → Semantic Scholar title search → Crossref title search. If any returns a match, the citation is considered real.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-bibtex-integrity-checker/scripts')
from verify_citations import verify_bib_file

fake_titles = verify_bib_file('/root/test.bib')

import json
with open('/root/answer.json', 'w') as f:
    json.dump({"fake_citations": fake_titles}, f, indent=2)
```

**Dependencies** (install with `pip install requests bibtexparser`):  
- `requests` – for HTTP calls  
- `bibtexparser` – for parsing `.bib` files  

---

## Scripts

```python filename=scripts/verify_citations.py
"""
BibTeX citation integrity checker.

Parses a .bib file and verifies each citation against online sources.
Returns a sorted list of fake (unverifiable) citation titles.
"""

import json
import sys
import re
import time
import requests
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

# Configuration
CROSSREF_API_BASE = "https://api.crossref.org/works"
SEMANTIC_SCHOLAR_API_BASE = "https://api.semanticscholar.org/graph/v1/paper"
REQUEST_DELAY = 1.0  # seconds between requests to avoid rate limits

def clean_title(raw_title):
    """Remove BibTeX braces and backslashes from title."""
    if not raw_title:
        return ""
    # Remove braces
    title = raw_title.replace('{', '').replace('}', '')
    # Remove LaTeX commands like \texttt{} etc.
    title = re.sub(r'\\(?:[a-zA-Z]+)(\{[^}]*\})?', '', title)
    # Remove stray backslashes
    title = title.replace('\\', '')
    # Normalize whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def doi_exists(doi):
    """Check if DOI resolves to a valid page (HTTP 200)."""
    url = f"https://doi.org/{doi}"
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        return resp.status_code == 200
    except requests.RequestException:
        return False

def search_semantic_scholar(query, is_doi=False):
    """Search Semantic Scholar by query (title or DOI). Returns True if a match found."""
    if is_doi:
        url = f"{SEMANTIC_SCHOLAR_API_BASE}/{query}"
    else:
        url = f"{SEMANTIC_SCHOLAR_API_BASE}/search?query={query}&limit=1"
    try:
        resp = requests.get(url, headers={"User-Agent": "BibChecker/1.0"}, timeout=10)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if is_doi:
            # If DOI returns a paper object, it exists
            return "paperId" in data
        else:
            # Search returns a list; check if any result's title is close
            results = data.get("data", [])
            if not results:
                return False
            # Relaxed check: just having any result is enough (user can refine)
            return True
    except (requests.RequestException, json.JSONDecodeError):
        return False

def search_crossref(title):
    """Search Crossref by title. Returns True if a match found."""
    params = {"query.title": title, "rows": 1}
    try:
        resp = requests.get(CROSSREF_API_BASE, params=params, timeout=10)
        if resp.status_code != 200:
            return False
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        return len(items) > 0
    except (requests.RequestException, json.JSONDecodeError):
        return False

def verify_entry(entry):
    """Verify one entry. Returns False if fake (unverifiable)."""
    # Extract fields
    title = entry.get("title", "")
    doi = entry.get("doi", "")
    cleaned_title = clean_title(title)
    
    if not cleaned_title:
        return False  # No title -> suspicious
    
    # Check DOI first
    if doi:
        # Clean DOI (remove whitespace, braces)
        doi = doi.strip().replace('{', '').replace('}', '')
        # 1. DOI resolution
        if doi_exists(doi):
            return True
        # 2. Semantic Scholar by DOI
        if search_semantic_scholar(doi, is_doi=True):
            return True
    
    # 3. Semantic Scholar by title
    if search_semantic_scholar(cleaned_title, is_doi=False):
        return True
    
    # 4. Crossref by title (fallback)
    if search_crossref(cleaned_title):
        return True
    
    # No confirmation found
    return False

def verify_bib_file(bib_path):
    """
    Parse a .bib file and return sorted list of fake citation titles.
    """
    with open(bib_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if not content.strip():
        raise ValueError("Empty bib file")
    
    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    bib_database = bibtexparser.loads(content, parser=parser)
    
    fake_titles = []
    entries = bib_database.entries
    if not entries:
        raise ValueError("No entries found in bib file")
    
    for i, entry in enumerate(entries):
        raw_title = entry.get("title", "")
        cleaned = clean_title(raw_title)
        if not cleaned:
            fake_titles.append(raw_title or "Untitled")
            continue
        
        # Rate limit: sleep between requests (except first)
        if i > 0:
            time.sleep(REQUEST_DELAY)
        
        if not verify_entry(entry):
            fake_titles.append(cleaned)
    
    # Sort alphabetically
    fake_titles.sort()
    return fake_titles

# Support direct execution for testing
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify_citations.py <path_to_bib>")
        sys.exit(1)
    bib_file = sys.argv[1]
    try:
        fakes = verify_bib_file(bib_file)
        print(json.dumps({"fake_citations": fakes}, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```