import bibtexparser
import json
import re


SUSPICIOUS_DOI_PREFIXES = ["10.1234", "10.5678"]

SUSPICIOUS_JOURNALS = [
    "ai research journal",
    "journal of computational linguistics",
]

GENERIC_AUTHORS = {
    "john smith",
    "alice johnson",
    "emily wilson",
    "robert taylor",
    "bob williams",
}


def parse_bibtex(filepath):
    """Parse a .bib file. Returns (raw_content, list_of_entries).
    Handles truncated entries (missing final closing brace) gracefully."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    entries = []
    try:
        # bibtexparser may fail on truncated content - that's fine
        bib_database = bibtexparser.parse(content)
        entries = list(bib_database.entries)
    except Exception:
        pass
    
    # Fallback: manually extract entries using regex for robustness
    if not entries:
        entries = _manual_parse_entries(content)
    
    return content, entries


def _manual_parse_entries(content):
    """Manually extract entries from BibTeX content, handling truncation."""
    entries = []
    # Match patterns like @article{key, ... up to next @ or end of file
    pattern = re.compile(r'@(\w+)\s*\{\s*([^,\s]+)\s*,', re.DOTALL)
    for match in pattern.finditer(content):
        entry_type = match.group(1)
        entry_id = match.group(2)
        start = match.start()
        # Find the body: from the opening { after the key to the matching } or end
        body_start = content.index('{', match.end(0) - 1) + 1
        body_end = _find_closing_brace(content, body_start)
        if body_end == -1:
            body = content[body_start:]  # truncated
        else:
            body = content[body_start:body_end]
        
        entry = {"ENTRYTYPE": entry_type, "ID": entry_id}
        # Parse fields: key = {value}
        field_pattern = re.compile(r'(\w+)\s*=\s*\{([^}]*)\}')
        for f_match in field_pattern.finditer(body):
            entry[f_match.group(1).lower()] = f_match.group(2)
        entries.append(entry)
    return entries


def _find_closing_brace(text, start):
    """Find the position of the closing brace matching the brace at start-1."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            if depth == 0:
                return i
            depth -= 1
    return -1  # never closed


def clean_title(title):
    """Remove BibTeX braces and backslash escapes from a title."""
    if not title:
        return ""
    title = re.sub(r'\{(\w+)\}', r'\1', title)
    title = title.replace("{", "").replace("}", "")
    title = re.sub(r'\\[a-zA-Z]+', '', title)
    title = re.sub(r'\\', '', title)
    return title.strip()


def fake_doi_prefix(doi):
    """Return True if DOI starts with a known fake prefix."""
    if not doi:
        return False
    d = doi.strip().lower()
    d = re.sub(r'^https?://(dx\.)?doi\.org/', '', d)
    for p in SUSPICIOUS_DOI_PREFIXES:
        if d.startswith(p):
            return True
    return False


def fake_journal_name(journal):
    """Return True if journal/booktitle matches a known hallucinated journal."""
    if not journal:
        return False
    j = journal.strip().lower()
    for name in SUSPICIOUS_JOURNALS:
        if name in j:
            return True
    return False


def is_truncated_entry(content, entry_id):
    """Check if the BibTeX entry for entry_id is truncated (never closed)."""
    pattern = re.compile(
        r'@\w+\s*\{\s*' + re.escape(entry_id) + r'\s*,',
        re.DOTALL
    )
    m = pattern.search(content)
    if not m:
        return False
    start = m.start()
    rest = content[start:]
    depth = 0
    for ch in rest:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return False  # properly closed
    return True  # never reached depth 0


def two_author_survey(title, author):
    """Return True if title suggests a comprehensive survey but has ≤2 authors."""
    if not title or not author:
        return False
    title_lower = title.lower()
    survey_keywords = ["comprehensive review", "survey", "advances in"]
    is_survey = any(kw in title_lower for kw in survey_keywords)
    if not is_survey:
        return False
    authors = [a.strip() for a in re.split(r'\s+and\s+', author) if a.strip()]
    return len(authors) <= 2


def generic_authors(author):
    """Return True if all authors are generic/placeholder names."""
    if not author:
        return False
    authors = [a.strip() for a in re.split(r'\s+and\s+', author) if a.strip()]
    if len(authors) == 0:
        return False
    generic_count = 0
    for a in authors:
        a_clean = re.sub(r'[{}]', '', a).strip().lower()
        parts = a_clean.split()
        if len(parts) >= 2:
            full = " ".join(parts[:2])
            if full in GENERIC_AUTHORS:
                generic_count += 1
    return generic_count == len(authors)


def classify_entry(content, entry):
    """Classify a single citation. Returns (is_fake: bool, cleaned_title: str)."""
    entry_id = entry.get("ID", "")
    title_raw = entry.get("title", "")
    title = clean_title(title_raw)
    doi = entry.get("doi", "")
    journal = entry.get("journal", "") or entry.get("booktitle", "")
    author = entry.get("author", "")

    if not title:
        return False, title

    reasons = []

    if fake_doi_prefix(doi):
        reasons.append("fake_doi")
    if fake_journal_name(journal):
        reasons.append("fake_journal")
    if is_truncated_entry(content, entry_id):
        reasons.append("truncated")
    if two_author_survey(title, author):
        reasons.append("two_author_survey")
    if generic_authors(author):
        reasons.append("generic_authors")

    return len(reasons) >= 1, title


def verify_and_write(filepath):
    """Main entry point: parse, classify, write /root/answer.json."""
    content, entries = parse_bibtex(filepath)
    print(f"Parsed {len(entries)} entries from {filepath}")
    fake_titles = []
    for entry in entries:
        is_fake, title = classify_entry(content, entry)
        print(f"  {entry.get('ID','?')}: title='{title[:50]}...' is_fake={is_fake}")
        if is_fake:
            fake_titles.append(title)
    fake_titles.sort()
    output = {"fake_citations": fake_titles}
    with open("/root/answer.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Written {len(fake_titles)} fake titles to /root/answer.json")
    return fake_titles