---
name: evo-create-hello-file
---

# Hello World File Creator

This skill creates a file named `hello.txt` with the exact content `"Hello, world!"` in the **current working directory**.

**Important**: The file must be created in the current working directory (i.e., the directory from which the script is run). Do **not** create it inside any subdirectory (like `app/` or any other folder). The path should be exactly `./hello.txt`.

## Functions

### `create_hello_file()`

Creates (or overwrites) a file named `hello.txt` with the content `"Hello, world!"` in the current working directory.

- **Inputs**: None.
- **Outputs**: Returns `True` on success, raises an exception on failure.
- **Location**: `scripts/utils.py`

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-create-hello-file/scripts')
from utils import create_hello_file

create_hello_file()
```

```python filename=scripts/utils.py
def create_hello_file():
    """Create hello.txt with "Hello, world!" content."""
    with open("hello.txt", "w") as f:
        f.write("Hello, world!")
    return True
```