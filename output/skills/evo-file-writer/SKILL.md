---
name: evo-file-writer
---

# File Writer

Creates text files with specified content. Use this skill whenever you need to generate a plain text file with given content. The skill provides a utility function and a ready-to-run script for common cases.

When the user says "create hello.txt with 'Hello, world!'", you must **immediately run** one of the following to produce the file:

1. **Run the provided script** – from the skill's directory:
   ```bash
   python /app/environment/skills/evo-file-writer/scripts/create_hello.py
   ```
   (this creates `hello.txt` in the current working directory)

2. **Or execute inline Python** (no import needed):
   ```python
   with open('hello.txt', 'w') as f:
       f.write('Hello, world!')
   ```

Use whichever approach is simpler for the context. The script is included for deterministic execution; the inline code is also perfectly fine.

## Functions

### create_text_file(filepath, content)

- **Inputs**: `filepath` (str) – path of the file to create; `content` (str) – text to write.
- **Outputs**: Confirmation string.
- **Purpose**: Writes content to a file in the current working directory.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-file-writer/scripts')
from utils import create_text_file
result = create_text_file('hello.txt', 'Hello, world!')
print(result)
```

```python filename=scripts/utils.py
def create_text_file(filepath: str, content: str) -> str:
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"Successfully created {filepath}"
```

```python filename=scripts/create_hello.py
#!/usr/bin/env python3
"""Creates hello.txt with 'Hello, world!' in the current directory."""
from pathlib import Path
Path('hello.txt').write_text('Hello, world!', encoding='utf-8')
print("Created hello.txt")
```