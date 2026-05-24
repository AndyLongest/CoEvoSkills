#!/usr/bin/env python3
"""
Verify BibTeX citations against CrossRef API.
Flags entries as fake if no matching work is found.
Output file is written with world-readable permissions (0o644).
"""

import json
import os
import re
import sys
import requests
import bibtexparser
from difflib import SequenceMatcher

CROSSREF_BASE = "https://api.crossref.org/works"
TIMEOUT = 10
TITLE_SIMILARITY_THRESHOLD = 0.85


def clean_title(title: str) -> str:
    """Remove BibTeX braces and escape sequences, then normalize whitespace."""
    cleaned = title.replace('{', '').replace('}', '')
    cleaned = re.sub(r'\\([a-zA-Z]+)', '', cleaned)
    cleaned = re.sub(r'[^a-zA-Z0-9\s\-:.,;!?()]', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
    return cleaned


def crossref_search(entry: dict) -> bool:
    """Search CrossRef for a BibTeX entry. Returns True if a matching work is found."""
    doi = entry.get('doi', '').strip()
    if doi:
        url = f"{CROSSREF_BASE}/{doi}"
        try:
            r = requests.get(url, timeout=TIMEOUT, headers={'User-Agent': 'CitationVerifier/1.0'})
            if r.status_code == 200:
                return True
        except Exception:
            pass

    title = clean_title(entry.get('title', ''))
    if not title:
        return False

    author_field = entry.get('author', '')
    first_author = ''
    if author_field:
        first_author = author_field.split(' and ')[0].strip()
        if ',' in first_author:
            first_author = first_author.split(',')[0].strip()
        else:
            first_author = first_author.split()[-1] if first_author.split() else ''

    params = {'query.title': title, 'rows': 10}
    if first_author:
        params['query.author'] = first_author

    try:
        r = requests.get(CROSSREF_BASE, params=params, timeout=TIMEOUT,
                         headers={'User-Agent': 'CitationVerifier/1.0'})
        if r.status_code != 200:
            return False
        data = r.json()
        items = data.get('message', {}).get('items', [])
        for item in items:
            item_title = clean_title(item.get('title', [''])[0])
            similarity = SequenceMatcher(None, title, item_title).ratio()
            if similarity >= TITLE_SIMILARITY_THRESHOLD:
                return True
            if title in item_title or item_title in title:
                return True
    except Exception:
        pass
    return False


def verify_citations(bib_filepath: str = '/root/test.bib',
                     output_filepath: str = '/root/answer.json') -> None:
    """Parse BibTeX, validate each entry, write results with world-readable permissions."""
    with open(bib_filepath, 'r', encoding='utf-8') as f:
        bib_data = bibtexparser.load(f)

    fake_citations = []
    for entry in bib_data.entries:
        raw_title = entry.get('title', '')
        clean = clean_title(raw_title)
        if not clean:
            continue
        if not crossref_search(entry):
            fake_citations.append(raw_title)

    # Clean titles for output: remove braces and escape sequences, keep original case
    output_titles = []
    for t in fake_citations:
        cleaned = t.replace('{', '').replace('}', '')
        cleaned = re.sub(r'\\([a-zA-Z])', r'\1', cleaned)
        cleaned = cleaned.replace('\\', '')
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned:
            output_titles.append(cleaned)

    output_titles.sort()

    result = {"fake_citations": output_titles}
    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    
    # Ensure world-readable permissions
    os.chmod(output_filepath, 0o644)

    print(f"Verification complete. Found {len(output_titles)} fake citations.")
    print(f"Results written to {output_filepath}")


if __name__ == '__main__':
    bib_path = sys.argv[1] if len(sys.argv) > 1 else '/root/test.bib'
    out_path = sys.argv[2] if len(sys.argv) > 2 else '/root/answer.json'
    verify_citations(bib_path, out_path)