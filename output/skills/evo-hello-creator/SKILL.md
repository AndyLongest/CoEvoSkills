---
name: evo-hello-creator
---

---
name: evo-hello-creator
description: Creates hello.txt files with "Hello, world!" content. Use when the task requires generating a simple greeting file.
---

# Hello Creator Skill

A simple skill for creating hello.txt files with "Hello, world!" content.

## Usage

Use the `write_hello()` function from `scripts/utils.py` to create the hello.txt file.

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-hello-creator/scripts')
from utils import write_hello
write_hello()
```

This will create `/root/hello.txt` with the content "Hello, world!". If the file already exists, it will be overwritten.
