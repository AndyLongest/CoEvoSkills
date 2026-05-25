from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

PROOT_URL = "https://github.com/proot-me/proot/releases/download/v5.3.0/proot-v5.3.0-x86_64-static"
PROOT_PATH = Path(__file__).parent / "proot"


class Sandbox:
    """Sandboxed execution environment.

    Supports three backends:
      - local:  Subprocess in temp dir with proot bind-mount for path virtualization
      - bare:   Plain subprocess in temp dir (fallback, no path virtualization)
      - docker: Full Docker container isolation (requires docker-py + daemon)
    """

    def __init__(self, image: str = "python:3.12-slim", backend: str = "local"):
        self.image = image
        self.backend = backend
        self._container: Any = None
        self._workspace: Path | None = None
        self._initialized = False

    def setup(self, install_deps: list[str] | None = None) -> None:
        """Initialize the sandbox environment. Idempotent — safe to call multiple times."""
        if self._initialized:
            return

        if self.backend == "docker":
            self._setup_docker()
        else:
            self._setup_local()

        if install_deps:
            deps_str = " ".join(install_deps)
            self.run(f"pip install -q {deps_str} 2>&1 | tail -5", timeout=300)

        self._initialized = True

    def _setup_local(self) -> None:
        self._workspace = Path(tempfile.mkdtemp(prefix="coevo_sandbox_"))
        for subdir in ("app", "root", "tests", "logs"):
            (self._workspace / subdir).mkdir(parents=True, exist_ok=True)

    def _setup_docker(self) -> None:
        import docker

        client = docker.from_env()
        volumes = {}
        self._workspace = Path(tempfile.mkdtemp(prefix="coevo_sandbox_"))
        volumes[str(self._workspace)] = {"bind": "/app", "mode": "rw"}
        self._container = client.containers.run(
            self.image,
            "sleep infinity",
            detach=True,
            remove=True,
            volumes=volumes,
            working_dir="/app",
        )

    def run(self, command: str, timeout: int = 60, cwd: str = "/app") -> tuple[int, str, str]:
        if not self._initialized:
            self.setup()

        commands = [c.strip() for c in command.strip().split("\n") if c.strip()]
        all_stdout: list[str] = []
        all_stderr: list[str] = []
        exit_code = 0

        for cmd in commands:
            ec, out, err = self._run_single(cmd, timeout=timeout, cwd=cwd)
            exit_code = ec
            all_stdout.append(out)
            all_stderr.append(err)
            if ec != 0:
                break

        return exit_code, "\n".join(all_stdout), "\n".join(all_stderr)

    def _run_single(self, command: str, timeout: int = 60, cwd: str = "/app") -> tuple[int, str, str]:
        if self.backend == "docker":
            return self._run_docker(command, timeout, cwd)
        return self._run_local(command, timeout, cwd)

    def _run_local(self, command: str, timeout: int, cwd: str) -> tuple[int, str, str]:
        if not self._workspace:
            return 1, "", "Sandbox not initialized"

        proot_bin = self._ensure_proot()

        try:
            if proot_bin:
                ws = str(self._workspace)
                proot_cmd = [
                    str(proot_bin),
                    "-b", f"{ws}/app:/app",
                    "-b", f"{ws}/root:/root",
                    "-b", f"{ws}/tests:/tests",
                    "-b", f"{ws}/logs:/logs",
                    "-w", cwd,
                    "bash", "-c", command,
                ]
                result = subprocess.run(
                    proot_cmd,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    env={**os.environ, "PROOT_NO_SECCOMP": "1"},
                )
            else:
                # Bare fallback: no path virtualization
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    cwd=str(self._workspace),
                    env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
                )

            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 124, "", f"Command timed out after {timeout}s"

    def _ensure_proot(self) -> Path | None:
        """Download proot static binary if not present. Returns path or None."""
        if PROOT_PATH.exists():
            return PROOT_PATH

        try:
            print(f"[sandbox] downloading proot from {PROOT_URL} ...")
            urlretrieve(PROOT_URL, PROOT_PATH)
            PROOT_PATH.chmod(PROOT_PATH.stat().st_mode | stat.S_IEXEC)
            print("[sandbox] proot ready")
            return PROOT_PATH
        except Exception as e:
            print(f"[sandbox] proot download failed: {e}, falling back to bare mode")
            return None

    def _run_docker(self, command: str, timeout: int, cwd: str) -> tuple[int, str, str]:
        try:
            result = self._container.exec_run(
                f"cd {cwd} && {command}",
                demux=True,
            )
            exit_code = result.exit_code or 0
            stdout = result.output[0].decode() if result.output and result.output[0] else ""
            stderr = result.output[1].decode() if result.output and len(result.output) > 1 and result.output[1] else ""
            return exit_code, stdout, stderr
        except Exception as e:
            return 1, "", str(e)

    def write_file(self, path: str, content: str) -> None:
        if not self._initialized:
            self.setup()

        full_path = self._workspace / path.lstrip("/")
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    def read_file(self, path: str) -> str:
        if not self._initialized:
            self.setup()

        full_path = self._workspace / path.lstrip("/")
        if not full_path.exists():
            return ""
        try:
            return full_path.read_text()
        except UnicodeDecodeError:
            return ""

    def file_exists(self, path: str) -> bool:
        if not self._initialized or not self._workspace:
            return False
        full_path = self._workspace / path.lstrip("/")
        return full_path.exists()

    def cleanup(self) -> None:
        if self.backend == "docker" and self._container:
            try:
                self._container.remove(force=True)
            except Exception:
                pass

        if self._workspace and self._workspace.exists():
            import shutil

            shutil.rmtree(self._workspace, ignore_errors=True)

        self._initialized = False
        self._workspace = None
        self._container = None
