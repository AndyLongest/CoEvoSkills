from __future__ import annotations

from utils.agent.loop import AgentLoop
from utils.agent.prompts import EXECUTE_ONLY_SYSTEM_PROMPT

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


class Oracle:
    """Ground-Truth Oracle (§3.3).

    Re-executes skill S(i) in a fresh, independent environment E' and
    returns only an opaque pass/fail signal R ∈ {0, 1}. The oracle
    never reveals test content or failure details.

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
            reward = self._run_verifier_tests(sandbox, task, timeout)

            sandbox.cleanup()
            return int(reward), float(reward)
        except Exception:
            sandbox.cleanup()
            return 0, 0.0

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
