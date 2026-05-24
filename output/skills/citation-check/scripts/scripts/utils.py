import bibtexparser
import re
import json
import requests
import sys

def clean_title(text):
    """Remove BibTeX formatting braces and escape sequences."""
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\\(?:textbackslash\s*)?', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_valid_doi(doi):
    """Check DOI existence via Crossref API. Returns True/False/None."""
    doi = doi.strip()
    if not doi.startswith('10.'):
        return False
    url = f'https://api.crossref.org/works/{doi}'
    try:
        resp = requests.get(url, timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return None  # network issue, fallback to heuristic

def heuristic_check(entry):
    """
    Return True if entry is likely fake based on missing or implausible fields.
    """
    title = entry.get('title', '')
    author = entry.get('author', '')
    year = entry.get('year', '')
    journal = entry.get('journal', entry.get('booktitle', ''))

    # Critical missing fields
    if not title or len(title.strip()) < 10:
        return True
    if not author:
        return True
    if not year:
        return True

    # Very generic journal name
    generic = {'unknown', 'journal', 'n/a', 'none', 'proceedings'}
    if journal and journal.lower().strip() in generic:
        return True

    return False

def verify_citations(bibtex_path):
    """
    Parse BibTeX file, validate citations, write /root/answer.json.
    Always produces the output file (empty list if no fake found).
    """
    fake_titles = []

    try:
        with open(bibtex_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Warning: File {bibtex_path} not found. Writing empty result.", file=sys.stderr)
        _write_output(fake_titles)
        return fake_titles
    except Exception as e:
        print(f"Warning: Could not read file: {e}. Writing empty result.", file=sys.stderr)
        _write_output(fake_titles)
        return fake_titles

    try:
        bib_database = bibtexparser.loads(content)
    except Exception as e:
        print(f"Warning: BibTeX parsing error: {e}. Writing empty result.", file=sys.stderr)
        _write_output(fake_titles)
        return fake_titles

    entries = bib_database.entries if hasattr(bib_database, 'entries') else []
    for entry in entries:
        raw_title = entry.get('title', '')
        if not raw_title:
            continue
        title = clean_title(raw_title)

        doi = entry.get('doi', '')

        doi_valid = False
        if doi:
            doi_valid = is_valid_doi(doi)

        if doi_valid is True:
            continue  # real citation
        elif doi_valid is False:
            fake_titles.append(title)
            continue
        else:
            # No network or no DOI: use heuristic
            if heuristic_check(entry):
                fake_titles.append(title)
                continue
            # else: assume real (cannot determine)

    fake_titles.sort()
    _write_output(fake_titles)
    return fake_titles

def _write_output(titles):
    """Write result to /root/answer.json (absolute path)."""
    result = {"fake_citations": titles}
    output_path = '/root/answer.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f"Results written to {output_path}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python utils.py <path_to_bibtex_file>", file=sys.stderr)
        sys.exit(1)
    verify_citations(sys.argv[1])