#!/usr/bin/env python3
"""Standalone runner for BibTeX citation verification."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import verify_and_write

fake_titles = verify_and_write("/root/test.bib")

print(f"\nVerification complete. Found {len(fake_titles)} fake citation(s).")
for t in fake_titles:
    print(f"  - {t}")

print(f"\nResults written to /root/answer.json")