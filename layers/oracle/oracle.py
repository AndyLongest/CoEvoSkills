from __future__ import annotations

import json as json_module
import logging
import subprocess
from pathlib import Path

from utils.agent.prompts import EXECUTE_ONLY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_STUB_APT = """\
#!/bin/bash
# Stub: skip apt-get (not available in sandbox)
exit 0
"""

_STUB_CURL = """\
#!/bin/bash
# Stub: skip curl-based uv install (pytest available via pip)
exit 0
"""

_CTRF_PATH = "/logs/verifier/ctrf.json"


class Oracle:
    """Ground-Truth Oracle (§3.3).

    Re-executes skill S(i) in a fresh, independent environment E' and
    returns (binary_int, float_score). When partial_credit=False (default),
    both values are 0 or 1. When partial_credit=True, float_score is the
    passed/total ratio from the test suite, and binary_int is 1 iff all
    tests passed.

    Steps:
      1. Create a fresh sandbox (separate from evolution sandbox).
      2. Prepare environment + install skill.
       3. Run opencode agent to produce outputs.
       4. Run ground-truth test suite.
      5. Read reward.
    """

    def evaluate(
        self,
        skill,
        task,
        client,
        deps: list[str] | None = None,
        timeout: int = 3600,
        partial_credit: bool = False,
        sandbox_backend: str = "docker",
        sandbox_image: str = "python:3.12-slim",
    ) -> tuple[int, float]:
        from utils.executor.sandbox import Sandbox

        sandbox = Sandbox(backend=sandbox_backend, image=sandbox_image)
        sandbox.setup(install_deps=deps)

        try:
            env = task.environment
            env.prepare_sandbox(sandbox)
            env.install_skill(sandbox, skill.name, skill)

            # Run opencode to produce outputs using the installed skill
            self._run_agent(sandbox, task, skill)

            # Run ground-truth tests
            self._run_verifier_tests(sandbox, task, timeout)

            if partial_credit:
                score = self._compute_partial_score(sandbox)
            else:
                score = float(self._read_reward(sandbox))

            sandbox.cleanup()
            return (1 if score >= 1.0 else 0), score
        except Exception:
            sandbox.cleanup()
            return 0, 0.0

    def _run_agent(self, sandbox, task, skill) -> None:
        """Run opencode in the Oracle sandbox using the installed skill.

        Creates a fresh opencode session in the isolated sandbox workspace.
        The agent executes the task using the pre-installed evo-* skill.
        Matches the paper's independent agent harness (Claude-Code/Codex)
        in a fresh environment E'.
        """
        workspace = sandbox._workspace / "app" if sandbox._workspace else None
        if workspace is None:
            logger.error("Oracle: no sandbox workspace, skipping agent execution")
            return

        agents_md = f"""\
# CoEvoSkills Oracle Agent

You execute tasks using pre-installed skills in an isolated sandbox.

## Task
{task.instruction}

## Available Skill
The skill '{skill.name}' is pre-installed at /app/environment/skills/{skill.name}/.
- Read /app/environment/skills/{skill.name}/SKILL.md for the skill documentation.
- Import skill functions:
    import sys; sys.path.insert(0, '/app/environment/skills/{skill.name}/scripts')
    from utils import function_name
- Write /root/run.py that imports and uses the skill functions.
- Run: python3 /root/run.py
- Output files go to /root/.

## Rules
- No sudo.
- Read available skills before executing.
- Input data is at /app/environment/data/ and /data/.
"""

        agents_path = workspace / "AGENTS.md"
        agents_path.parent.mkdir(parents=True, exist_ok=True)
        agents_path.write_text(agents_md)

        try:
            subprocess.run(
                [
                    "opencode",
                    "run",
                    task.instruction,
                    "--model",
                    "deepseek/deepseek-v4-pro",
                    "--agent",
                    "coevo-evolution",
                    "--dir",
                    str(workspace),
                    "--format",
                    "json",
                ],
                check=False,
                timeout=600,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Oracle: opencode timed out")
        except Exception as e:
            logger.warning("Oracle: opencode error: %s", e)

    def _run_verifier_tests(self, sandbox, task, timeout: int) -> None:
        """Run ground-truth test suite in the sandbox."""
        test_dir = task.verifier_path.parent
        if not test_dir.exists():
            return

        for test_file in test_dir.iterdir():
            if test_file.is_file():
                content = test_file.read_text()
                sandbox.write_file(f"/tests/{test_file.name}", content)

        sandbox.run("cp -rn /root/* /app/ 2>/dev/null; cp -rn /app/* /root/ 2>/dev/null", timeout=5)

        if sandbox.backend != "docker":
            sandbox.write_file("/root/bin/apt-get", _STUB_APT)
            sandbox.write_file("/root/bin/apt", _STUB_APT)
            sandbox.write_file("/root/bin/curl", _STUB_CURL)
            sandbox.run("chmod +x /root/bin/apt-get /root/bin/apt /root/bin/curl", timeout=5)
            sandbox.run(
                "export PATH=/root/bin:$PATH && bash /tests/test.sh 2>&1",
                timeout=min(timeout, 600),
            )
        else:
            sandbox.run(
                "bash /tests/test.sh 2>&1",
                timeout=min(timeout, 600),
            )

    def _read_reward(self, sandbox) -> int:
        """Read binary reward from reward.txt."""
        reward_text = sandbox.read_file("/logs/verifier/reward.txt").strip()
        try:
            return int(float(reward_text))
        except (ValueError, TypeError):
            return 0

    def _compute_partial_score(self, sandbox) -> float:
        """Compute partial credit from CTRF JSON test report.

        Returns passed/total ratio, e.g. 0.75 for 6/8 tests passing.
        Falls back to binary reward.txt if CTRF is unavailable.
        """
        ctrf_text = sandbox.read_file(_CTRF_PATH).strip()
        if not ctrf_text:
            logger.warning("ORACLE: CTRF report not found at %s, falling back to binary reward", _CTRF_PATH)
            return float(self._read_reward(sandbox))

        try:
            report = json_module.loads(ctrf_text)
            summary = report.get("results", {}).get("summary", {})
            passed = int(summary.get("passed", 0))
            total = int(summary.get("total", 0))
            if total == 0:
                return float(self._read_reward(sandbox))
            return passed / total
        except (json_module.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning("ORACLE: failed to parse CTRF report: %s, falling back to binary reward", e)
            return float(self._read_reward(sandbox))
