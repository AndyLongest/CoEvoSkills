from __future__ import annotations

import json as json_module
import logging

from utils.agent.loop import AgentLoop
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
      3. Run AgentLoop to produce outputs.
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
    ) -> tuple[int, float]:
        from utils.executor.sandbox import Sandbox

        sandbox = Sandbox()
        sandbox.setup(install_deps=deps)

        try:
            env = task.environment
            env.prepare_sandbox(sandbox)
            env.install_skill(sandbox, skill.name, skill)

            # Run agent to produce outputs
            prompt = EXECUTE_ONLY_SYSTEM_PROMPT.replace("{skill_name}", skill.name)
            agent = AgentLoop(client=client, sandbox=sandbox, system_prompt=prompt, max_turns=10)
            agent.init_context(task.instruction)
            agent.run_loop(task.instruction)

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

    def _run_verifier_tests(self, sandbox, task, timeout: int) -> None:
        """Run ground-truth test suite in the sandbox.

        test.sh assumes Docker (apt-get, curl, uv). We stub those out
        and let the script run as-is — the core test logic (pytest, python3)
        works fine without root.
        """
        test_dir = task.verifier_path.parent
        if not test_dir.exists():
            return

        # Copy test files into sandbox
        for test_file in test_dir.iterdir():
            if test_file.is_file():
                content = test_file.read_text()
                sandbox.write_file(f"/tests/{test_file.name}", content)

        # Sync files between /root/ and /app/ so tests find outputs either way
        sandbox.run("cp -rn /root/* /app/ 2>/dev/null; cp -rn /app/* /root/ 2>/dev/null", timeout=5)

        # Create stub scripts to shadow apt-get and curl (Docker-only commands)
        sandbox.write_file("/root/bin/apt-get", _STUB_APT)
        sandbox.write_file("/root/bin/apt", _STUB_APT)
        sandbox.write_file("/root/bin/curl", _STUB_CURL)
        sandbox.run("chmod +x /root/bin/apt-get /root/bin/apt /root/bin/curl", timeout=5)

        # Run test.sh with stubs on PATH
        sandbox.run(
            "export PATH=/root/bin:$PATH && bash /tests/test.sh 2>&1",
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

    def _run_verifier_tests(self, sandbox, task, timeout: int) -> int:
        """Run ground-truth test suite in the sandbox.

        test.sh assumes Docker (apt-get, curl, uv). We stub those out
        and let the script run as-is — the core test logic (pytest, python3)
        works fine without root.
        """
        test_dir = task.verifier_path.parent
        if not test_dir.exists():
            return 0

        # Copy test files into sandbox
        for test_file in test_dir.iterdir():
            if test_file.is_file():
                content = test_file.read_text()
                sandbox.write_file(f"/tests/{test_file.name}", content)

        # Sync files between /root/ and /app/ so tests find outputs either way
        sandbox.run("cp -rn /root/* /app/ 2>/dev/null; cp -rn /app/* /root/ 2>/dev/null", timeout=5)

        # Create stub scripts to shadow apt-get and curl (Docker-only commands)
        sandbox.write_file("/root/bin/apt-get", _STUB_APT)
        sandbox.write_file("/root/bin/apt", _STUB_APT)
        sandbox.write_file("/root/bin/curl", _STUB_CURL)
        sandbox.run("chmod +x /root/bin/apt-get /root/bin/apt /root/bin/curl", timeout=5)

        # Run test.sh with stubs on PATH
        ec, stdout, stderr = sandbox.run(
            "export PATH=/root/bin:$PATH && bash /tests/test.sh 2>&1",
            timeout=min(timeout, 600),
        )

        reward_text = sandbox.read_file("/logs/verifier/reward.txt").strip()
        try:
            return int(float(reward_text))
        except (ValueError, TypeError):
            return 0
