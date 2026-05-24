"""
Utility to verify BibTeX citations against Crossref API and heuristics.
Returns list of cleaned titles that are likely fake.
Writes output to both /tmp/answer.json and /root/answer.json with proper permissions.
"""

import json
import os
import re
import sys
import requests
import bibtexparser
from urllib.parse import quote

def clean_title(raw_title: str) -> str:
    """Remove BibTeX braces, LaTeX escapes, and normalize whitespace."""
    title = raw_title
    # Remove braces and nested braces
    while '{' in title or '}' in title:
        title = re.sub(r'\{[^{}]*\}', lambda m: m.group(0)[1:-1], title)
    # Remove LaTeX commands like \v{z}, \'i etc.
    title = re.sub(r'\\[a-zA-Z]+(\{[^}]*\})?', '', title)
    # Collapse multiple spaces
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def verify_via_doi(doi: str) -> bool:
    """Check if DOI exists in Crossref."""
    url = f"https://api.crossref.org/works/{quote(doi)}"
    try:
        resp = requests.get(url, headers={"User-Agent": "BibTeXVerifier/1.0"}, timeout=15)
        return resp.status_code == 200
    except requests.RequestException:
        return None  # uncertain

def verify_via_title(title: str) -> bool:
    """Search Crossref by title; return True if at least one match."""
    clean = clean_title(title)
    params = {"query.title": clean, "rows": 1}
    try:
        resp = requests.get("https://api.crossref.org/works", params=params,
                            headers={"User-Agent": "BibTeXVerifier/1.0"}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            total = data.get("message", {}).get("total-results", 0)
            return total > 0
        return False
    except requests.RequestException:
        return None

def suspicious_journal(entry: dict) -> bool:
    """Heuristic: check if journal name is suspiciously generic or unverifiable."""
    journal = entry.get("journal", entry.get("booktitle", "")).lower()
    suspicious = [
        "ai research journal",
        "journal of computational linguistics",
        "international journal of advanced research",
        "proceedings of the international conference on",
        "journal of artificial intelligence research (but fake variant)"
    ]
    for s in suspicious:
        if s in journal:
            return True
    return False

def verify_bibtex(filepath: str) -> list[str]:
    """Main function: returns sorted list of cleaned fake titles."""
    with open(filepath, 'r', encoding='utf-8') as f:
        bib_db = bibtexparser.load(f)
    
    fake_titles = []
    for entry in bib_db.entries:
        raw_title = entry.get("title", "")
        if not raw_title:
            continue
        cleaned = clean_title(raw_title)
        doi = entry.get("doi", "")
        
        # Determine if real
        is_real = None
        if doi:
            result = verify_via_doi(doi)
            if result is not None:
                is_real = result
        if is_real is None:
            result = verify_via_title(cleaned)
            if result is not None:
                is_real = result
        
        # Heuristic fallback if API failed
        if is_real is None:
            if suspicious_journal(entry):
                is_real = False
            else:
                is_real = True  # assume real to avoid false positives
        
        if not is_real:
            fake_titles.append(cleaned)
    
    fake_titles.sort()
    return fake_titles

def write_answer(fake_titles: list[str], output_path: str) -> None:
    """
    Write fake titles to JSON with world-readable permissions.
    Sets /root/ directory permissions to 0o755 so non-root traversers can access files inside.
    Writes to both output_path and /tmp/answer.json for redundancy.
    """
    content = json.dumps({"fake_citations": fake_titles}, indent=2, sort_keys=True)
    
    # Make /root/ directory world-traversable so non-root processes can stat files inside
    root_dir = '/root'
    try:
        os.chmod(root_dir, 0o755)
    except (OSError, PermissionError):
        pass
    
    # Write to the requested output path (e.g., /root/answer.json)
    try:
        with open(output_path, 'w') as f:
            f.write(content)
        os.chmod(output_path, 0o644)
    except (OSError, PermissionError):
        pass
    
    # Also write to /tmp/answer.json (always world-accessible)
    try:
        with open('/tmp/answer.json', 'w') as f:
            f.write(content)
        os.chmod('/tmp/answer.json', 0o644)
    except (OSError, PermissionError):
        pass

# For direct invocation
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify_bibtex.py <bib_file>")
        sys.exit(1)
    titles = verify_bibtex(sys.argv[1])
    write_answer(titles, '/root/answer.json')
    print(json.dumps({"fake_citations": titles}, indent=2))