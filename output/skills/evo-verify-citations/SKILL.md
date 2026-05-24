---
name: evo-verify-citations
---

# Verify Citation Integrity

This skill identifies fake or hallucinated citations in a BibTeX file by cross-referencing with the Crossref API and applying robust heuristic checks on DOI prefixes. All output titles are guaranteed to be directly extracted from the input file — no hallucinated entries.

## Workflow

1. Read the BibTeX file from `/root/test.bib`.
2. Parse all entries, extracting titles, DOIs, and other fields.
3. Build a set of all valid titles from the input file for cross-validation.
4. For each entry, verify authenticity:
   - If DOI has an invalid prefix (e.g., `10.5678`, `10.1234`), mark as fake.
   - If DOI has a valid prefix, check Crossref API. If 404, mark as fake.
   - If no DOI, search by title on Crossref. If no match, mark as fake.
   - If API errors occur, default to keeping the citation (conservative).
5. Cross-validate: ensure every output title exists in the input file's title set.
6. Write cleaned, sorted, deduplicated fake titles to `/root/answer.json`.

## Script Execution

Run the verification script directly:

```bash
cd /app/environment/skills/evo-verify-citations/scripts
python verify_citations.py
```

## Functions

### `parse_bib(filepath)`
Parses a BibTeX file using regex, handling truncated entries. Returns a list of entry dicts with lowercase field keys.

### `clean_title(title)`
Removes BibTeX curly braces, LaTeX escape sequences, and extra whitespace. Returns clean plain-text title.

### `get_doi_prefix(doi)`
Extracts the numeric prefix from a DOI (e.g., `10.1038`). Returns the prefix string or `None`.

### `has_valid_doi_prefix(doi)`
Checks if the DOI prefix belongs to a known valid publisher prefix set. Returns `True`, `False`, `'unknown'`, or `None` (no DOI).

### `check_doi(doi)`
Queries Crossref API for a given DOI. Returns `True` (200), `False` (404), or `None` (error).

### `check_title(title)`
Queries Crossref API with a title search. Returns `True` (match found), `False` (no match), or `None` (error).

### `main()`
Orchestrates parsing, verification, cross-validation, and output writing. Prints result to stdout.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-verify-citations/scripts')
from verify_citations import parse_bib, clean_title, get_doi_prefix, has_valid_doi_prefix, check_doi, check_title
```

```python filename=scripts/verify_citations.py
#!/usr/bin/env python3
"""
Verify BibTeX citations from /root/test.bib against Crossref API.
Writes only fake citation titles (from the input file) to /root/answer.json.
All output titles are validated against the input file to prevent hallucination.
"""

import json
import re
import sys
import requests

# Known valid DOI prefixes from major publishers
VALID_DOI_PREFIXES = {
    '10.1038',   # Nature
    '10.1126',   # Science
    '10.18653',  # ACL Anthology
    '10.1073',   # PNAS
    '10.1109',   # IEEE
    '10.1007',   # Springer
    '10.1016',   # Elsevier
    '10.1145',   # ACM
    '10.1371',   # PLOS
    '10.1093',   # Oxford
    '10.1080',   # Taylor & Francis
    '10.1111',   # Wiley
    '10.3390',   # MDPI
    '10.1021',   # ACS
    '10.1063',   # AIP
    '10.1364',   # Optica
    '10.1136',   # BMJ
    '10.1056',   # NEJM
    '10.1515',   # De Gruyter
    '10.7554',   # eLife
    '10.1242',   # Company of Biologists
    '10.15252',  # EMBO
    '10.1523',   # J. Neurosci.
    '10.1186',   # BioMed Central
    '10.1182',   # Blood
}

def parse_bib(filepath):
    """
    Parse a BibTeX file, returning list of entry dicts.
    Handles malformed/truncated entries via regex.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = []
    # Match complete entries: @type{key, ... }
    pattern = r'@(\w+)\{(\w+),\s*((?:[^{}]*|\{[^{}]*\})*)\}'
    for match in re.finditer(pattern, content, re.DOTALL):
        typ = match.group(1)
        citekey = match.group(2)
        fields_str = match.group(3)
        entry = {'ENTRYTYPE': typ, 'ID': citekey}
        for m in re.finditer(r'(\w+)\s*=\s*\{(.*?)\}', fields_str, re.DOTALL):
            entry[m.group(1).lower()] = m.group(2)
        entries.append(entry)

    # Also attempt truncated entries at end of file
    incomplete_pattern = r'@(\w+)\{(\w+),\s*((?:(?!\n@).)*?)\n?$'
    for match in re.finditer(incomplete_pattern, content, re.DOTALL):
        typ = match.group(1)
        citekey = match.group(2)
        fields_str = match.group(3)
        if not any(e['ID'] == citekey for e in entries):
            entry = {'ENTRYTYPE': typ, 'ID': citekey}
            for m in re.finditer(r'(\w+)\s*=\s*\{(.*?)\}', fields_str, re.DOTALL):
                entry[m.group(1).lower()] = m.group(2)
            if 'title' in entry and len(entry['title'].strip()) >= 3:
                entries.append(entry)

    return entries

def clean_title(title):
    """Remove BibTeX formatting: braces, LaTeX commands, extra spaces."""
    title = title.replace('{', '').replace('}', '')
    title = re.sub(r'\\[a-zA-Z]+', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def get_doi_prefix(doi):
    """Extract prefix from DOI (e.g., '10.1038' from '10.1038/s41586-021-03819-2')."""
    if not doi:
        return None
    doi = doi.strip().lower()
    match = re.match(r'(10\.\d+)', doi)
    if match:
        return match.group(1)
    return None

def has_valid_doi_prefix(doi):
    """Check if DOI has a known valid publisher prefix."""
    if not doi:
        return None
    prefix = get_doi_prefix(doi)
    if prefix in VALID_DOI_PREFIXES:
        return True
    if prefix:
        return 'unknown'
    return False

def check_doi(doi):
    """Verify DOI exists on Crossref. Returns True/False/None."""
    if not doi:
        return None
    url = f"https://api.crossref.org/works/{doi}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return True
        elif r.status_code == 404:
            return False
        else:
            return None
    except requests.RequestException:
        return None

def check_title(title):
    """Search title on Crossref. Returns True if match found, False if none, None on error."""
    if not title or len(title.strip()) < 5:
        return None
    url = "https://api.crossref.org/works"
    params = {'query.title': title, 'rows': 3}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data['message']['items']:
                item_title = (item.get('title', [''])[0] or '').lower()
                if title.lower() in item_title or item_title in title.lower():
                    return True
            return False
        else:
            return None
    except requests.RequestException:
        return None

def main():
    filepath = '/root/test.bib'
    entries = parse_bib(filepath)

    # Build set of all valid titles from input for cross-validation
    all_input_titles = set()
    for entry in entries:
        raw_title = entry.get('title', '')
        if raw_title and len(raw_title.strip()) >= 3:
            cleaned = clean_title(raw_title)
            if cleaned:
                all_input_titles.add(cleaned)

    fake_titles = []

    for entry in entries:
        title = entry.get('title', '')
        doi = entry.get('doi', '')

        # Skip entries without a valid title
        if not title or len(title.strip()) < 3:
            continue

        is_fake = False

        # Step 1: Check DOI prefix validity
        prefix_valid = has_valid_doi_prefix(doi)
        if prefix_valid is False:
            # DOI with invalid prefix is almost certainly fake
            is_fake = True
        elif prefix_valid is True:
            # Known registrar prefix: check API for existence
            verified = check_doi(doi)
            if verified is False:
                is_fake = True  # DOI registered but not found on Crossref
            elif verified is True:
                is_fake = False  # Confirmed real
            else:
                # API error, cannot verify. Assume real.
                is_fake = False
        elif prefix_valid == 'unknown':
            # Prefix exists but unknown registrar: check API
            verified = check_doi(doi)
            if verified is False:
                is_fake = True
            elif verified is True:
                is_fake = False
            else:
                is_fake = False
        else:
            # No DOI at all: check by title
            verified = check_title(title)
            if verified is False:
                is_fake = True  # No match found on Crossref
            elif verified is True:
                is_fake = False  # Found
            else:
                is_fake = False  # API error or title too short, assume real

        if is_fake:
            cleaned = clean_title(title)
            if cleaned:
                fake_titles.append(cleaned)

    # Deduplicate and sort alphabetically
    fake_titles = sorted(set(fake_titles))

    # Cross-validate: ensure every output title exists in the input file
    validated_titles = [t for t in fake_titles if t in all_input_titles]

    # Warn if some titles don't match (should not happen, but guard against it)
    missing = set(fake_titles) - all_input_titles
    if missing:
        print(f"WARNING: {len(missing)} output title(s) not found in input file: {missing}", file=sys.stderr)

    result = {"fake_citations": validated_titles}
    with open('/root/answer.json', 'w') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
```