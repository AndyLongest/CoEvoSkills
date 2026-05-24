"""
BibTeX citation verifier.
Detects fake/hallucinated citations using CrossRef API + conservative heuristics.
Ensures every output title exists in the original BibTeX file.

Usage:
    python verify_bib.py /root/test.bib /root/answer.json
"""
import re
import json
import sys
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
FAKE_DOI_PREFIXES = {'10.1234', '10.5678', '10.0000'}
GENERIC_AUTHORS = [
    'john smith', 'alice johnson', 'bob williams', 'jane doe',
    'emily wilson', 'robert taylor', 'sarah lee', 'michael brown',
    'lisa davis', 'david miller', 'mary wilson', 'tom jones',
    'aisha patel', 'carlos ramirez'
]


def clean_title(raw):
    """Remove BibTeX braces, backslash escapes, collapse whitespace."""
    if not raw or not isinstance(raw, str):
        return ''
    t = raw.replace('{', '').replace('}', '')
    t = re.sub(r'\\(.)', r'\1', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _get(value):
    """Get first non-None string from bibtexparser field."""
    if value is None:
        return ''
    if isinstance(value, list):
        return str(value[0]) if value else ''
    return str(value)


def doi_exists(doi):
    """Check CrossRef for DOI. Returns True (200), False (404), None (error)."""
    if not doi or not doi.strip():
        return None
    try:
        r = requests.get(f"{CROSSREF_BASE}/{quote(doi.strip())}", timeout=10)
        if r.status_code == 200:
            return True
        elif r.status_code == 404:
            return False
        return None
    except Exception:
        return None


def title_exists(title, author='', year=''):
    """Search CrossRef by title. Returns True (found), False (not found), None (error)."""
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
        r = requests.get(CROSSREF_BASE, params=params, timeout=10)
        if r.status_code != 200:
            return None
        items = r.json().get('message', {}).get('items', [])
        if not items:
            return False
        first = _get(items[0].get('title', ['']))
        if first:
            t1 = title.lower().strip()
            t2 = first.lower().strip()
            if t1 in t2 or t2 in t1:
                return True
            w1 = set(t1.split())
            w2 = set(t2.split())
            if w1 and w2 and len(w1 & w2) / max(len(w1), len(w2)) >= 0.5:
                return True
        return False
    except Exception:
        return None


def is_fake_by_heuristic(entry):
    """Conservative heuristic: only flag with strong evidence."""
    title = _get(entry.get('title'))
    author = _get(entry.get('author'))
    year = _get(entry.get('year'))
    doi = _get(entry.get('doi'))

    if not title:
        return False

    # Missing BOTH author and year (incomplete entry)
    if not author and not year:
        return True

    # Check DOI prefix
    is_fake_doi = False
    if doi:
        prefix = doi.split('/')[0].strip().lower()
        if prefix in FAKE_DOI_PREFIXES:
            is_fake_doi = True

    # Check generic author
    is_generic = False
    if author:
        al = author.lower()
        for g in GENERIC_AUTHORS:
            if g in al:
                is_generic = True
                break

    # Fake DOI + generic author
    if is_fake_doi and is_generic:
        return True

    return False


def parse_bibtex(text):
    """Parse BibTeX text. Returns list of entry dicts."""
    entries = []

    # Try bibtexparser
    if HAS_BIBTEX:
        try:
            db = bibtexparser.loads(text)
            for e in db.entries:
                entries.append(e)
            if entries:
                return entries
        except Exception:
            pass

    # Regex fallback
    text_clean = re.sub(r'(?m)^%.*$', '', text)

    # Complete entries
    pat = r'@(\w+)\{(\w+)\s*,\s*(.*?)\}'
    for m in re.finditer(pat, text_clean, re.DOTALL):
        fields = m.group(3)
        entry = {'ID': m.group(2), 'ENTRYTYPE': m.group(1)}
        for fld in ['title', 'author', 'year', 'doi', 'journal', 'booktitle',
                     'publisher', 'address', 'pages', 'volume', 'number']:
            fm = re.search(rf'{fld}\s*=\s*\{{([^}}]*)\}}', fields, re.IGNORECASE | re.DOTALL)
            if fm:
                entry[fld] = fm.group(1).strip()
        entries.append(entry)

    # Truncated entries
    trunc = r'@(\w+)\{(\w+)\s*,\s*(.*?)$'
    seen = {e.get('ID') for e in entries if e.get('ID')}
    for m in re.finditer(trunc, text_clean, re.MULTILINE | re.DOTALL):
        key = m.group(2)
        if key and key not in seen:
            fields = m.group(3)
            entry = {'ID': key, 'ENTRYTYPE': m.group(1)}
            for fld in ['title', 'author', 'year', 'doi', 'journal', 'booktitle',
                         'publisher', 'address', 'pages', 'volume', 'number']:
                fm = re.search(rf'{fld}\s*=\s*\{{([^}}]*)\}}', fields, re.IGNORECASE | re.DOTALL)
                if fm:
                    entry[fld] = fm.group(1).strip()
            if 'title' not in entry:
                entry['title'] = ''
            entries.append(entry)

    return entries


def detect_fake_citations(bib_path, output_path):
    """Main detection: parse, validate, write. Validates output against bib file."""
    with open(bib_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Extract all valid titles from the file
    all_entries = parse_bibtex(text)
    valid_titles = set()
    for e in all_entries:
        t = _get(e.get('title', ''))
        if t:
            valid_titles.add(clean_title(t))

    fake_titles = []

    for entry in all_entries:
        raw_title = _get(entry.get('title', ''))
        if not raw_title:
            continue
        cleaned = clean_title(raw_title)

        # Use API if available
        if HAS_REQUESTS:
            doi = _get(entry.get('doi', ''))
            author = _get(entry.get('author', ''))
            year = _get(entry.get('year', ''))

            doi_result = doi_exists(doi) if doi else None
            if doi_result is True:
                continue
            elif doi_result is False:
                fake_titles.append(cleaned)
                continue

            title_result = title_exists(raw_title, author, year)
            if title_result is True:
                continue
            elif title_result is False:
                if is_fake_by_heuristic(entry) and cleaned:
                    fake_titles.append(cleaned)
                continue

            # Network error: use heuristic
            if is_fake_by_heuristic(entry) and cleaned:
                fake_titles.append(cleaned)
        else:
            if is_fake_by_heuristic(entry) and cleaned:
                fake_titles.append(cleaned)

    # Deduplicate, filter to only valid titles, sort
    fake_titles = sorted(set(f for f in fake_titles if f in valid_titles))

    _write(fake_titles, output_path)
    return fake_titles


def heuristic_only(bib_path):
    """Offline heuristic detection. Returns sorted fake titles."""
    with open(bib_path, 'r', encoding='utf-8') as f:
        text = f.read()

    entries = parse_bibtex(text)
    valid_titles = set()
    for e in entries:
        t = _get(e.get('title', ''))
        if t:
            valid_titles.add(clean_title(t))

    fake = []
    for entry in entries:
        t = _get(entry.get('title', ''))
        if not t:
            continue
        if is_fake_by_heuristic(entry):
            cleaned = clean_title(t)
            if cleaned:
                fake.append(cleaned)

    return sorted(set(f for f in fake if f in valid_titles))


def _write(titles, path):
    """Write output JSON."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({"fake_citations": titles}, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    bib_path = sys.argv[1] if len(sys.argv) > 1 else '/root/test.bib'
    out_path = sys.argv[2] if len(sys.argv) > 2 else '/root/answer.json'
    detect_fake_citations(bib_path, out_path)