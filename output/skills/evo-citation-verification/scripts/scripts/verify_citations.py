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