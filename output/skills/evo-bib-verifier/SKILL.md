---
name: evo-bib-verifier
---

# BibTeX Citation Verifier

Verify the integrity of a BibTeX bibliography by detecting fake or hallucinated citations. This skill loads a BibTeX file, validates each citation against the Crossref API, and identifies entries that do not correspond to real academic publications.

## Workflow

1. Parse the BibTeX file using `bibtexparser`.
2. For each entry, attempt to retrieve metadata from Crossref:
   - If the entry has a DOI, use `/works/{doi}`.
   - Otherwise, use `/works?query.title={title}&query.author={author}`.
3. If Crossref returns a 404, no results, or a mismatch (e.g., completely different title), mark the citation as fake.
4. Write the sorted list of fake citation titles to `/root/answer.json`.

## Functions

### `load_bibtex(filepath) -> list[dict]`
- **Input**: Path to a `.bib` file.
- **Output**: List of parsed entries, each with keys like `title`, `author`, `doi`, `year`, etc.

### `validate_citation(entry) -> bool`
- **Input**: A single BibTeX entry dict.
- **Output**: `True` if the citation appears real (Crossref returns a matching record), `False` if it appears fake.

### `clean_title(raw_title) -> str`
- **Input**: Raw title string with possible LaTeX formatting.
- **Output**: Clean title (removes braces, backslashes, etc.).

### `check_bib_integrity(filepath) -> list[str]`
- **Input**: Path to `.bib` file.
- **Output**: Alphabetically sorted list of cleaned titles of fake citations.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-bib-verifier/scripts')
from utils import check_bib_integrity

fake_titles = check_bib_integrity('/root/test.bib')
```

```python filename=scripts/utils.py
import requests
import bibtexparser
import re
import json
import time

def load_bibtex(filepath):
    """Parse a BibTeX file and return list of entries."""
    with open(filepath, 'r', encoding='utf-8') as f:
        bib_database = bibtexparser.load(f)
    return bib_database.entries

def clean_title(raw_title):
    """Remove LaTeX braces and backslashes from a title."""
    if not raw_title:
        return ""
    # Remove braces
    cleaned = re.sub(r'[\{\}]', '', raw_title)
    # Remove backslash commands but keep text after (e.g., \v{Z} -> Z)
    cleaned = re.sub(r'\\[a-zA-Z]+(?:\{[^}]*\})?', '', cleaned)
    # Replace multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def validate_citation(entry, timeout=5, max_retries=2):
    """
    Check if a BibTeX entry corresponds to a real publication via Crossref API.
    Returns True if real, False if fake.
    """
    title = entry.get('title', '')
    doi = entry.get('doi', '')
    author = entry.get('author', '')  # may have braces, but we'll use raw

    headers = {'User-Agent': 'BibVerifier/1.0 (mailto:example@example.com)'}

    if doi:
        # Use DOI endpoint
        url = f"https://api.crossref.org/works/{doi}"
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    # Check that returned title matches (approximately)
                    returned_title = data.get('message', {}).get('title', [None])[0]
                    if returned_title:
                        cleaned_returned = clean_title(returned_title)
                        cleaned_input = clean_title(title)
                        # Allow small differences but if completely different, it's fake
                        if cleaned_returned.lower() == cleaned_input.lower() or \
                           cleaned_input.lower() in cleaned_returned.lower() or \
                           cleaned_returned.lower() in cleaned_input.lower():
                            return True
                    # If DOI exists but title mismatches, likely fake
                    return False
                elif resp.status_code == 404:
                    return False
                else:
                    # Maybe rate limited, wait and retry
                    time.sleep(1)
            except requests.exceptions.RequestException:
                time.sleep(1)
        return False  # after retries, assume fake
    else:
        # Search by title
        search_title = clean_title(title)
        params = {
            'query.title': search_title,
            'rows': 3
        }
        if author:
            # Simple author name extraction (take first author's last name)
            first_author = author.split(' and ')[0].strip()
            # Remove possible braces
            first_author = re.sub(r'[\{\}]', '', first_author)
            # Take last word (surname)
            parts = first_author.split(',')
            if len(parts) > 1:
                surname = parts[0].strip()
            else:
                surname = parts[-1].strip()
            if surname:
                params['query.author'] = surname

        for attempt in range(max_retries):
            try:
                resp = requests.get("https://api.crossref.org/works", params=params, headers=headers, timeout=timeout)
                if resp.status_code == 200:
                    items = resp.json().get('message', {}).get('items', [])
                    for item in items:
                        returned_title = item.get('title', [None])[0]
                        if returned_title:
                            cleaned_returned = clean_title(returned_title)
                            cleaned_input = clean_title(title)
                            if cleaned_returned.lower() == cleaned_input.lower() or \
                               cleaned_input.lower() in cleaned_returned.lower() or \
                               cleaned_returned.lower() in cleaned_input.lower():
                                return True
                    # No match found
                    return False
                else:
                    time.sleep(1)
            except requests.exceptions.RequestException:
                time.sleep(1)
        return False

def check_bib_integrity(filepath):
    """Main function: returns sorted list of cleaned fake citation titles."""
    entries = load_bibtex(filepath)
    fake_titles = []
    for entry in entries:
        if not validate_citation(entry):
            title = clean_title(entry.get('title', ''))
            if title:
                fake_titles.append(title)
    # Sort alphabetically
    fake_titles.sort()
    return fake_titles

# If run directly, test on /root/test.bib and write answer
if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        bib_path = sys.argv[1]
    else:
        bib_path = '/root/test.bib'
    fake = check_bib_integrity(bib_path)
    output = {'fake_citations': fake}
    with open('/root/answer.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Found {len(fake)} fake citations. Written to /root/answer.json")
```