#!/usr/bin/env python3
"""Verify BibTeX citations. Output: /root/answer.json. Always produces valid JSON."""

import bibtexparser
from bibtexparser.bparser import BibTexParser
import re, sys, os, json, tempfile
from datetime import datetime

OUT = '/root/answer.json'
INP = '/root/test.bib'

def clean(t):
    if not t: return ''
    t = t.replace('{', '').replace('}', '')
    t = re.sub(r'\\([a-zA-Z]+)\s*', '', t)
    return re.sub(r'\s+', ' ', t).strip()

def load(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        p = BibTexParser(common_strings=True)
        db = bibtexparser.load(f, parser=p)
    out = []
    for e in db.entries:
        n = {k.lower(): v for k, v in e.items()}
        n['type'] = e.get('ENTRYTYPE', '')
        out.append(n)
    return out

def bad(e):
    req = ['title', 'author', 'year']
    if e.get('type') in ('article', 'inproceedings', 'conference'):
        if 'journal' not in e and 'booktitle' not in e:
            return True
    for f in req:
        if f not in e or not e[f]:
            return True
    t, a, y = e.get('title', ''), e.get('author', ''), e.get('year', '')
    for p in [r'^undefined$', r'^unknown$', r'^title$', r'^test$', r'^\d+$',
              r'^[^a-zA-Z]{5,}$', r'\bplaceholder\b', r'\bdummy\b']:
        if re.search(p, t.strip(), re.I):
            return True
    if not re.search(r'[A-Z]', a): return True
    if ',' not in a and ' and ' not in a and len(a.split()) < 2: return True
    if re.match(r'^[a-zA-Z0-9]{20,}$', a): return True
    if y:
        try:
            yy = int(y); n = datetime.now().year
            if yy < 1800 or yy > n + 2: return True
        except: return True
    v = e.get('volume', '')
    if v:
        try:
            vv = int(v)
            if vv == 0 or vv > 1000: return True
        except: pass
    pgs = e.get('pages', '')
    if pgs:
        if not re.match(r'^\d+\s*[-–]\s*\d+$', pgs): return True
        parts = re.split(r'[-–]', pgs)
        if len(parts) == 2:
            try:
                s, en = int(parts[0].strip()), int(parts[1].strip())
                if s > en or en - s > 500: return True
            except: return True
    doi = e.get('doi', '')
    if doi and (not doi.startswith('10.') or '/' not in doi): return True
    return False

def main():
    path = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1][0] != '-' else INP
    entries = load(path)
    fakes = []
    for e in entries:
        if bad(e):
            t = clean(e.get('title', ''))
            if t: fakes.append(t)
    fakes.sort()
    out = {'fake_citations': fakes}
    
    # Write to temp first, then rename to prevent truncation
    fd, tmp = tempfile.mkstemp(dir='/root', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(json.dumps(out, indent=2))
        # Verify
        with open(tmp, 'r') as f:
            json.load(f)
        os.replace(tmp, OUT)
    except:
        if os.path.exists(tmp): os.unlink(tmp)
        raise
    
    print(f'Written {len(fakes)} to {OUT}')
    sys.exit(0)

if __name__ == '__main__':
    main()