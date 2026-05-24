#!/usr/bin/env python3
"""Creates hello.txt with 'Hello, world!' in the current directory."""
from pathlib import Path
Path('hello.txt').write_text('Hello, world!', encoding='utf-8')
print("Created hello.txt")