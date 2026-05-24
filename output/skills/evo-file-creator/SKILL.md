---
name: evo-file-creator
---

# File Creator Skill

This skill provides a simple utility to create text files with specified content. Use it whenever a task requires creating a new text file, such as configuration files, scripts, or simple documents.

## Functions

### `create_text_file(path, content)`
Creates a text file at the given path with the specified content. Overwrites the file if it already exists.

- **Inputs**:  
  - `path` (str): File path (relative or absolute).  
  - `content` (str): Content to write into the file.
- **Outputs**: None (writes the file).
- **Purpose**: Provides deterministic, reusable file creation to avoid repeatedly writing `open()` calls.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-file-creator/scripts')
from utils import create_text_file
create_text_file('hello.txt', 'Hello, world!')
```

```python filename=scripts/utils.py
def create_text_file(path, content):
    with open(path, 'w') as f:
        f.write(content)
```