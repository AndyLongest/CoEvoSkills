"""
Heuristic-based detection of fake citations (no network required).
Flags entries with:
- Suspicious DOI prefixes (10.1234, 10.5678, 10.0000)
- Missing title, author, or year
- Generic author names
- Incomplete entries (missing closing brace)
Usage:
    from heuristic_check import heuristic_check
    fake_titles = heuristic_check('/root/test.bib')
"""
import re
import json
import bibtexparser

SUSPICIOUS_DOI_PREFIXES = {'10.1234', '10.5678', '10.0000'}
GENERIC_NAMES = ['john smith', 'alice johnson', 'bob williams']

def _clean_title(title):
    if not title:
        return ""
    cleaned = title.replace('{', '').replace('}', '').replace('\\', '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def _is_suspicious_entry(entry):
    title = entry.get('title', '')
    author = entry.get('author', '')
    year = entry.get('year', '')
    doi = entry.get('doi', '')
    
    # Missing title
    if not title:
        return True
    
    # Suspicious DOI prefix
    if doi:
        prefix = doi.split('/')[0].lower()
        if prefix in SUSPICIOUS_DOI_PREFIXES:
            return True
    
    # Missing required fields (author, year)
    if not author or not year:
        return True
    
    # Generic name
    author_lower = author.lower()
    for generic in GENERIC_NAMES:
        if generic in author_lower:
            return True
    
    return False

def heuristic_check(bib_path):
    """Return sorted list of fake citation titles based on heuristics."""
    with open(bib_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try to parse; if fails, use regex fallback
    try:
        bib_db = bibtexparser.loads(content)
    except Exception:
        return _fallback_heuristic(content)
    
    fake_titles = []
    for entry in bib_db.entries:
        if _is_suspicious_entry(entry):
            title = _clean_title(entry.get('title', ''))
            if title:
                fake_titles.append(title)
    fake_titles.sort()
    return fake_titles

def _fallback_heuristic(content):
    """Parse incomplete content with regex."""
    pattern = r'@\w+\{(\w+),\s*([^}]*?)\}'
    entries = re.findall(pattern, content, re.DOTALL)
    fake_titles = []
    for key, fields in entries:
        # Extract title
        title_match = re.search(r'title\s*=\s*\{(.*?)\}', fields, re.DOTALL | re.IGNORECASE)
        title = title_match.group(1) if title_match else ''
        doi_match = re.search(r'doi\s*=\s*\{(.*?)\}', fields, re.DOTALL | re.IGNORECASE)
        doi = doi_match.group(1) if doi_match else ''
        author_match = re.search(r'author\s*=\s*\{(.*?)\}', fields, re.DOTALL | re.IGNORECASE)
        author = author_match.group(1) if author_match else ''
        year_match = re.search(r'year\s*=\s*\{(.*?)\}', fields, re.DOTALL | re.IGNORECASE)
        year = year_match.group(1) if year_match else ''
        entry = {'title': title, 'author': author, 'year': year, 'doi': doi}
        if _is_suspicious_entry(entry):
            cleaned = _clean_title(title)
            if cleaned:
                fake_titles.append(cleaned)
    fake_titles.sort()
    return fake_titles