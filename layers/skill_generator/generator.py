from __future__ import annotations

import logging
from pathlib import Path
from collections.abc import Callable

from repository.skill import SkillBundle
from utils.agent.loop import AgentLoop
from utils.agent.prompts import EVOLUTION_AGENT_SYSTEM_PROMPT
from utils.colors import C
from utils.executor.sandbox import Sandbox
from utils.llm.client import LLMClient
from utils.llm.types import Message

logger = logging.getLogger(__name__)


class SkillGenerator:
    """Skill Generator πθ (§3.3 Eq.7).

    Uses an AgentLoop in the sandbox to generate, execute, and refine skill
    bundles. The AgentLoop runs the EVOLUTION_AGENT_SYSTEM_PROMPT (P1-P6)
    workflow — creating skills, executing them, and learning from terminal
    output including import errors, API timeouts, and runtime failures.

    This unifies the Generator and Executor into a single AgentLoop session,
    matching the paper's design where the Evolution Agent has full sandbox
    access for both skill creation and execution.
    """

    def __init__(self, client: LLMClient, meta_skill: str = "", max_turns: int = 20):
        self.client = client
        self.meta_skill = meta_skill
        self.max_turns = max_turns
        self._agent_loop: AgentLoop | None = None
        self._skill_loader: Callable[[str], str | None] | None = None

    def set_skill_loader(self, loader: Callable[[str], str | None]) -> None:
        self._skill_loader = loader

    def generate_and_execute(
        self,
        instruction: str,
        sandbox: Sandbox,
        env_context: str = "",
        installed_tools: str = "",
        feedback: str | None = None,
    ) -> tuple[SkillBundle | None, dict[str, str]]:
        """Generate/refine skill and execute it in the sandbox.

        Initial call creates the AgentLoop and produces S(0) + x(0).
        Subsequent calls with feedback refine S in the existing conversation.

        Returns (skill_bundle, outputs) where outputs is {relative_path: content}.
        """
        if self._agent_loop is None:
            self._agent_loop = AgentLoop(
                client=self.client,
                sandbox=sandbox,
                system_prompt=EVOLUTION_AGENT_SYSTEM_PROMPT,
                max_turns=self.max_turns,
                command_timeout=120,
            )
            if self._skill_loader:
                self._agent_loop.set_skill_loader(self._skill_loader)
            self._agent_loop.init_context(
                instruction,
                meta_skill=self.meta_skill,
                env_files=env_context,
                installed_tools=installed_tools,
            )
            print(f"  {C.cyan('GENERATOR')} | AgentLoop initialized")

        if feedback:
            self._agent_loop._messages.append(Message.user(
                f"Host verifier found failures in the previous skill execution. "
                f"Fix the evo-* skill to address these issues, then re-execute "
                f"to produce output files. Here is the diagnostic:\n\n{feedback}"
            ))
            self._agent_loop._estimated_tokens += len(feedback) // 4

        print(f"  {C.cyan('GENERATOR')} | Running AgentLoop (max {self.max_turns} turns)...")
        self._agent_loop.run_loop(instruction)

        # Collect outputs from sandbox
        outputs = _collect_outputs(sandbox)
        print(f"  {C.cyan('GENERATOR')} | AgentLoop complete: {len(outputs)} files: {list(outputs.keys())[:5]}")

        # Extract skill from sandbox
        skill = _read_skill_from_sandbox(sandbox)
        if skill:
            print(f"  {C.cyan('GENERATOR')} | Skill '{skill.name}' found in sandbox")
        else:
            print(f"  {C.cyan('GENERATOR')} | No evo-* skill found in sandbox — using fallback")
            skill = SkillBundle(name="evo-task", skillell="# Fallback skill\n")

        return skill, outputs

    def append_oracle_signal(self, score: float) -> None:
        """Append oracle score to AgentLoop conversation context.

        score ∈ [0, 1]: fraction of ground-truth tests that passed.
        Uses the score to give the agent directional feedback:
          1.0   → "ALL TESTS PASSED. Converged."
          0.75  → "9/12 tests passed (75.0%). The oracle detected issues."
          0.0   → "ALL TESTS FAILED."
        """
        if self._agent_loop is None:
            return

        if score >= 1.0:
            signal = "Ground-truth oracle: ALL TESTS PASSED. Converged."
        elif score > 0.0:
            # Try to reconstruct passed/total from score for a more informative signal
            pct = score * 100
            signal = (
                f"Ground-truth oracle: {pct:.1f}% of tests passed. "
                f"The oracle detected remaining issues — escalate and improve."
            )
        else:
            signal = "Ground-truth oracle: ALL TESTS FAILED. Escalate and improve."

        self._agent_loop._messages.append(Message.user(signal))
        self._agent_loop._estimated_tokens += len(signal) // 4

    def context_usage_ratio(self) -> float:
        """Return estimated context window usage proportion."""
        if self._agent_loop:
            return self._agent_loop.context_usage_ratio()
        return 0.0

    @property
    def persisted_context(self) -> bool:
        """Whether the AgentLoop has been initialized (context persists)."""
        return self._agent_loop is not None


def _collect_outputs(sandbox: Sandbox) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for search_dir in ["/root", "/app"]:
        ec, stdout, _ = sandbox.run(
            f"find {search_dir} -maxdepth 3 \\( -type f -o -type l \\) "
            f"-not -path '*/.venv/*' -not -path '*/__pycache__/*' 2>/dev/null",
            timeout=30,
        )
        if ec == 0 and stdout:
            for line in stdout.strip().split("\n"):
                abspath = line.strip()
                if abspath and "progress.md" not in abspath:
                    content = sandbox.read_file(abspath)
                    # Include file even if content is empty (e.g., binary xlsx)
                    # as long as the file exists on disk.
                    if content is not None and (content or sandbox.file_exists(abspath)):
                        outputs[abspath.lstrip("/")] = content
    return outputs


def _read_skill_from_sandbox(sandbox: Sandbox) -> SkillBundle | None:
    ec, stdout, _ = sandbox.run(
        "find /app/environment/skills -name 'SKILL.md' -path '*/evo-*' 2>/dev/null",
        timeout=5,
    )
    if ec != 0 or not stdout:
        return None

    skillell_path = stdout.strip().split("\n")[0]
    if not skillell_path:
        return None

    skillell = sandbox.read_file(skillell_path)
    if not skillell:
        return None

    parts = Path(skillell_path).parts
    skill_name = "evo-task"
    for i, p in enumerate(parts):
        if p == "skills" and i + 1 < len(parts):
            skill_name = parts[i + 1]
            break

    scripts_dir = str(Path(skillell_path).parent / "scripts")
    ec2, out2, _ = sandbox.run(
        f"find {scripts_dir} -type f -not -name '*.pyc' 2>/dev/null", timeout=5
    )
    scripts: dict[str, str] = {}
    if ec2 == 0 and out2:
        for script_path in out2.strip().split("\n"):
            if not script_path.strip():
                continue
            try:
                content = sandbox.read_file(script_path.strip())
            except UnicodeDecodeError:
                continue
            if content:
                scripts[str(Path(script_path.strip()).relative_to(scripts_dir))] = content

    return SkillBundle(name=skill_name, skillell=skillell, scripts=scripts)
