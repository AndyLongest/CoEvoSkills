"""
Detect fake/hallucinated citations in a BibTeX file.
Validates against CrossRef API, with heuristic fallback.
Writes result to JSON file.

Usage:
    from fake_citation_detector import detect_fake_citations
    detect_fake_citations('/path/to/test.bib', '/path/to/answer.json')
"""
import re
import json
import time
from urllib.parse import quote

try:
    import bibtexparser
    HAS_BIBTEX = True
except ImportError:
    HAS_BIBTEX = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

CROSSREF_BASE = "https://api.crossref.org/works"
SUSPICIOUS_DOI_PREFIXES = {'10.1234', '10.5678', '10.0000'}
GENERIC_AUTHOR_TOKENS = [
    'john smith', 'alice johnson', 'bob williams', 'jane doe',
    'emily wilson', 'robert taylor', 'tom jones', 'sarah lee',
    'michael brown', 'lisa davis', 'david miller', 'mary wilson'
]
SUSPICIOUS_JOURNAL_TOKENS = [
    'ai research journal', 'journal of computational examples',
    'international journal of artificial intelligence and machine learning',
    'advances in artificial intelligence', 'journal of machine learning and applications'
]


def _clean_title(title):
    """Remove BibTeX braces, backslash formatting, and extra whitespace."""
    if not title or not isinstance(title, str):
        return ""
    # Remove braces
    cleaned = title.replace('{', '').replace('}', '')
    # Remove backslash escape sequences like \\v, \\' etc.
    cleaned = re.sub(r'\\(.)', r'\1', cleaned)
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _validate_doi(doi):
    """Check if a DOI exists via CrossRef API. Returns True if valid, False if not, None on error."""
    if not doi:
        return None
    url = f"{CROSSREF_BASE}/{quote(doi.strip())}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return True
        elif resp.status_code == 404:
            return False
        else:
            return None
    except Exception:
        return None


def _search_by_title_and_author(title, author=None, year=None):
    """Search CrossRef by title and optionally author/year. Returns True if found, False if not, None on error."""
    if not title:
        return None
    params = {"query.title": title}
    if author:
        params["query.author"] = author
    if year:
        try:
            y = int(year)
            params["filter"] = f"from-pub-date:{y}-01-01,until-pub-date:{y}-12-31"
        except (ValueError, TypeError):
            pass
    try:
        resp = requests.get(CROSSREF_BASE, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data.get('message', {}).get('items', [])
        if not items:
            return False
        # Check if first result has a similar title
        first_title = items[0].get('title', [None])[0]
        if first_title:
            t1 = title.lower().strip()
            t2 = first_title.lower().strip()
            # Simple similarity: substring or high overlap
            if t1 in t2 or t2 in t1:
                return True
            # Word overlap
            words1 = set(t1.split())
            words2 = set(t2.split())
            if len(words1) > 0 and len(words2) > 0:
                overlap = len(words1 & words2) / max(len(words1), len(words2))
                if overlap >= 0.5:
                    return True
        return False
    except Exception:
        return None


def _is_definitely_fake(entry):
    """Strong evidence that entry is fake. Must satisfy multiple criteria."""
    title = entry.get('title', '')
    author = entry.get('author', '')
    year = entry.get('year', '')
    doi = entry.get('doi', '')
    journal = entry.get('journal', '') or entry.get('booktitle', '')

    if not title:
        return False  # can't flag without a title

    # Check for suspicious DOI prefix
    suspicious_doi = False
    if doi:
        prefix = doi.split('/')[0].strip().lower()
        if prefix in SUSPICIOUS_DOI_PREFIXES:
            suspicious_doi = True

    # Check for generic author names
    generic_author = False
    if author:
        author_lower = author.lower()
        for generic in GENERIC_AUTHOR_TOKENS:
            if generic in author_lower:
                generic_author = True
                break

    # Check for suspicious journal
    suspicious_journal = False
    if journal:
        journal_lower = journal.lower()
        for tok in SUSPICIOUS_JOURNAL_TOKENS:
            if tok in journal_lower:
                suspicious_journal = True
                break

    # Missing years or authors
    missing_required = not author or not year

    # Strong pattern 1: suspicious DOI + generic author
    if suspicious_doi and generic_author:
        return True

    # Strong pattern 2: suspicious DOI + missing required fields
    if suspicious_doi and missing_required:
        return True

    # Strong pattern 3: generic author + suspicious journal (no valid DOI)
    if generic_author and suspicious_journal and not doi:
        return True

    # Strong pattern 4: missing required fields + generic author
    if missing_required and generic_author:
        return True

    # Weak signals alone are not enough
    return False


def _extract_raw_entries(bib_str):
    """Fallback regex-based parser for malformed BibTeX. Returns list of dicts with title, author, year, doi."""
    # Remove comments
    bib_str = re.sub(r'%.*$', '', bib_str, flags=re.MULTILINE)
    entries = []

    # Pattern for complete entries
    pattern = r'@(\w+)\{([^,]*),\s*(.*?)\}'
    for match in re.finditer(pattern, bib_str, re.DOTALL):
        entry_type = match.group(1)
        key = match.group(2).strip()
        fields_str = match.group(3)
        entry = {'key': key, 'type': entry_type}
        for field in ['title', 'author', 'year', 'doi', 'journal', 'booktitle', 'publisher', 'address']:
            fm = re.search(
                rf'{re.escape(field)}\s*=\s*\{{([^}}]*)\}}',
                fields_str, re.IGNORECASE | re.DOTALL
            )
            if fm:
                entry[field] = fm.group(1).strip()
        entries.append(entry)

    # Handle truncated entries (no closing brace)
    trunc_pattern = r'@(\w+)\{([^,]*),\s*(.*?)$'
    processed_keys = {e.get('key') for e in entries if e.get('key')}
    for match in re.finditer(trunc_pattern, bib_str, re.MULTILINE | re.DOTALL):
        key = match.group(2).strip()
        if key and key not in processed_keys:
            entry = {'key': key, 'type': match.group(1)}
            fields_str = match.group(3)
            for field in ['title', 'author', 'year', 'doi', 'journal', 'booktitle', 'publisher', 'address']:
                fm = re.search(
                    rf'{re.escape(field)}\s*=\s*\{{([^}}]*)\}}',
                    fields_str, re.IGNORECASE | re.DOTALL
                )
                if fm:
                    entry[field] = fm.group(1).strip()
            if 'title' not in entry:
                # Check if first field might be title without label
                first_field_match = re.match(r'\s*([^=]+?)\s*=', fields_str)
                if first_field_match:
                    possible_field = first_field_match.group(1).strip().lower()
                    if possible_field not in ['author', 'year', 'doi', 'journal', 'booktitle', 'publisher', 'address', 'editor', 'pages', 'volume', 'number', 'month', 'note', 'url', 'isbn', 'issn']:
                        entry['title'] = possible_field
            entries.append(entry)

    return entries


def detect_fake_citations(bib_path, output_path):
    """Main function: parse .bib, validate entries, write fake citations to JSON."""
    with open(bib_path, 'r', encoding='utf-8') as f:
        bib_str = f.read()

    fake_titles = []

    # Parse entries
    raw_entries = []
    if HAS_BIBTEX:
        try:
            bib_db = bibtexparser.loads(bib_str)
            for entry in bib_db.entries:
                raw_entries.append(entry)
        except Exception:
            raw_entries = _extract_raw_entries(bib_str)
    else:
        raw_entries = _extract_raw_entries(bib_str)

    if not raw_entries:
        raw_entries = _extract_raw_entries(bib_str)

    for entry in raw_entries:
        title = entry.get('title', '')
        if not title:
            continue  # can't list a fake without a title

        cleaned = _clean_title(title)

        # Step 1: Check with definitive heuristics (catches obvious fakes)
        is_fake_heuristic = _is_definitely_fake(entry)

        # Step 2: Network check (if available)
        if HAS_REQUESTS:
            doi = entry.get('doi', '')
            author = entry.get('author', '')
            year = entry.get('year', '')

            doi_result = _validate_doi(doi) if doi else None
            if doi_result is True:
                # DOI confirmed real, not fake
                continue
            elif doi_result is False:
                # DOI does not exist -> fake (if it has a DOI)
                if cleaned:
                    fake_titles.append(cleaned)
                continue
            # doi_result is None (network error or no DOI)
            # Try title/author search
            title_result = _search_by_title_and_author(title, author, year)
            if title_result is True:
                # Found via title search, not fake
                continue
            elif title_result is False:
                # Not found via title search but could still be real (not indexed)
                # Only flag if heuristic also says fake
                if is_fake_heuristic and cleaned:
                    fake_titles.append(cleaned)
                continue
            # title_result is None (network error)
            # Fall back to heuristic
            if is_fake_heuristic and cleaned:
                fake_titles.append(cleaned)
        else:
            # No network: use heuristic only
            if is_fake_heuristic and cleaned:
                fake_titles.append(cleaned)

    # Dedup and sort
    fake_titles = sorted(set(fake_titles))
    _write_output(fake_titles, output_path)
    return fake_titles


def heuristic_check(bib_path):
    """Run heuristic-only detection (no network). Returns sorted list of fake titles."""
    with open(bib_path, 'r', encoding='utf-8') as f:
        bib_str = f.read()

    fake_titles = []

    if HAS_BIBTEX:
        try:
            bib_db = bibtexparser.loads(bib_str)
            for entry in bib_db.entries:
                if _is_definitely_fake(entry):
                    title = _clean_title(entry.get('title', ''))
                    if title:
                        fake_titles.append(title)
            return sorted(set(fake_titles))
        except Exception:
            pass

    # Fallback regex parsing
    raw_entries = _extract_raw_entries(bib_str)
    for entry in raw_entries:
        if _is_definitely_fake(entry):
            title = _clean_title(entry.get('title', ''))
            if title:
                fake_titles.append(title)
    return sorted(set(fake_titles))


def _write_output(fake_titles, output_path):
    """Write result to JSON file."""
    output = {"fake_citations": fake_titles}
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


# CLI entry point
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python fake_citation_detector.py <bib_path> [output_path]")
        sys.exit(1)
    bib_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else '/root/answer.json'
    detect_fake_citations(bib_path, output_path)