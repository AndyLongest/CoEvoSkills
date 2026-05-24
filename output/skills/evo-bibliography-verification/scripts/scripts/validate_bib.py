"""
Validate BibTeX citations by checking DOIs and titles against CrossRef API.
Usage:
    from validate_bib import validate_bib
    validate_bib('/path/to/test.bib', '/path/to/answer.json')
"""
import bibtexparser
import json
import requests
import re
import time
from urllib.parse import quote

CROSSREF_BASE = "https://api.crossref.org/works"

def _clean_title(title):
    """Remove BibTeX braces and backslash formatting."""
    if not title:
        return ""
    cleaned = title.replace('{', '').replace('}', '').replace('\\', '')
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def _validate_doi(doi):
    """Check if a DOI exists via CrossRef API. Returns True if valid."""
    url = f"{CROSSREF_BASE}/{quote(doi.strip())}"
    try:
        resp = requests.get(url, timeout=10)
        return resp.status_code == 200
    except requests.RequestException:
        return None  # network error, inconclusive

def _search_by_title(title, author=None, year=None):
    """Search CrossRef by title and optionally author/year. Returns True if found."""
    params = {"query.title": title}
    if author:
        params["query.author"] = author
    if year:
        params["filter"] = f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31"
    try:
        resp = requests.get(CROSSREF_BASE, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data.get('message', {}).get('items', [])
        if not items:
            return False
        # Check if first result has similar title (simple Jaccard? just check substring)
        first_title = items[0].get('title', [None])[0]
        if first_title and (title.lower() in first_title.lower() or first_title.lower() in title.lower()):
            return True
        return False
    except requests.RequestException:
        return None

def validate_bib(bib_path, output_path):
    """Main function: parse .bib, validate entries, write fake citations to JSON."""
    with open(bib_path, 'r', encoding='utf-8') as f:
        bib_str = f.read()
    
    # Attempt to parse – handle incomplete entries by capturing raw entries
    fake_titles = []
    
    # Use bibtexparser with a lenient parsing strategy
    try:
        bib_db = bibtexparser.loads(bib_str)
    except Exception as e:
        # Fallback: parse manually using regex for incomplete entries
        fake_titles = _fallback_parse(bib_str)
        _write_output(fake_titles, output_path)
        return fake_titles

    for entry in bib_db.entries:
        # Check required fields
        title = entry.get('title', '')
        if not title:
            fake_titles.append("")  # will be filtered later
            continue
        
        doi = entry.get('doi', '')
        author = entry.get('author', '')
        year = entry.get('year', '')
        
        # If DOI exists, validate it
        if doi:
            result = _validate_doi(doi)
            if result is False:
                fake_titles.append(_clean_title(title))
                continue
            elif result is True:
                continue  # real
            # result is None (network error) -> fall through to title search
        
        # No DOI or network issue: try title/author search
        search_result = _search_by_title(title, author, year)
        if search_result is False:
            fake_titles.append(_clean_title(title))
        elif search_result is None:
            # Network error, cannot determine; if heuristics are needed, we could mark as uncertain
            # For safety, skip (do not flag without evidence)
            pass
        
        # Rate limit
        time.sleep(0.1)
    
    fake_titles = [t for t in fake_titles if t]  # remove empties
    fake_titles.sort()
    _write_output(fake_titles, output_path)
    return fake_titles

def _fallback_parse(bib_str):
    """Simple regex-based parsing for incomplete BibTeX. Extracts entry keys and titles."""
    import re
    # Pattern to capture @type{key, ... title={...} ... }
    pattern = r'@\w+\{(\w+),\s*[^}]*?title\s*=\s*\{(.*?)\}'
    matches = re.findall(pattern, bib_str, re.DOTALL | re.IGNORECASE)
    fake_titles = []
    for key, title in matches:
        cleaned = _clean_title(title)
        if cleaned:
            fake_titles.append(cleaned)
    # For entries without title (like the truncated clue entry), include key as placeholder
    clue_pattern = r'@\w+\{(\w+),\s*[^}]*\}\)?'  # simple capture of key
    keys = re.findall(clue_pattern, bib_str, re.DOTALL)
    # But we cannot confirm those; we'll skip them in this fallback
    return sorted(set(fake_titles))

def _write_output(fake_titles, output_path):
    output = {"fake_citations": fake_titles}
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)