from __future__ import annotations

from pathlib import Path

from utils.executor.sandbox import Sandbox


class FileSystem:
    """File I/O abstraction for sandbox environments.

    Provides read/write/list operations that work transparently
    inside the sandbox.
    """

    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    def read(self, path: str | Path) -> str:
        return self._sandbox.read_file(str(path))

    def write(self, path: str | Path, content: str) -> None:
        self._sandbox.write_file(str(path), content)

    def exists(self, path: str | Path) -> bool:
        return self._sandbox.file_exists(str(path))

    def list_dir(self, path: str | Path) -> list[str]:
        exit_code, stdout, _ = self._sandbox.run(f"ls -1 {path} 2>/dev/null")
        if exit_code != 0 or not stdout:
            return []
        return [line.strip() for line in stdout.strip().split("\n") if line.strip()]

    def mkdir(self, path: str | Path) -> None:
        self._sandbox.run(f"mkdir -p {path}")
