from __future__ import annotations

import logging
from pathlib import Path
from collections.abc import Callable

from repository.skill import SkillBundle
from utils.agent.opencode_harness import EVOLUTION_AGENTS_MD, OpenCodeHarness, OpenCodeResult
from utils.colors import C
from utils.executor.sandbox import Sandbox
from utils.llm.client import LLMClient

logger = logging.getLogger(__name__)


def _build_agents_md(
    instruction: str,
    available_skills: dict[str, str] | None = None,
    feedback: str | None = None,
) -> str:
    """Build AGENTS.md content with task instructions for opencode.

    Only includes skill names+descriptions and the task instruction.
    The agent explores the environment itself using read/glob/bash tools,
    matching the paper's Claude-Code/Codex behavior.
    """

    parts = [EVOLUTION_AGENTS_MD]

    if available_skills:
        lines = [
            "\n## Pre-installed Skills",
            "",
            "Read SKILL.md files in /app/environment/skills/ to load these:",
            "",
        ]
        for name, desc in available_skills.items():
            lines.append(f"- **{name}**: {desc}")
            lines.append(f"  /app/environment/skills/{name}/SKILL.md")
            lines.append("")
        parts.extend(lines)

    if feedback:
        parts.append(f"## Previous Run Feedback\n\n{feedback}")
        parts.append("Fix the skill to address these issues, then re-execute.")

    parts.append(f"\n## Task\n\n{instruction}")

    return "\n\n".join(parts)


class SkillGenerator:
    """Skill Generator πθ (§3.3 Eq.7).

    Uses OpenCodeHarness (opencode CLI) as the execution engine.
    The harness provides native tool calling, workspace awareness, session
    management, and sub-agent delegation — matching Claude-Code/Codex
    capabilities from the paper.

    AGENTS.md is written to the sandbox workspace before each run, providing
    opencode with structured task instructions, available skills, environment
    context, and progress tracking requirements.
    """

    def __init__(self, client: LLMClient, meta_skill: str = "", max_turns: int = 20):
        self.client = client
        self.meta_skill = meta_skill
        self.max_turns = max_turns
        self._harness: OpenCodeHarness | None = None
        self._skill_loader: Callable[[str], str | None] | None = None
        self._workspace: Path | None = None
        self._last_result: OpenCodeResult | None = None

    def set_skill_loader(self, loader: Callable[[str], str | None]) -> None:
        self._skill_loader = loader

    def generate_and_execute(
        self,
        instruction: str,
        sandbox: Sandbox,
        feedback: str | None = None,
        available_skills: dict[str, str] | None = None,
    ) -> tuple[SkillBundle | None, dict[str, str]]:
        """Generate/refine skill and execute via opencode harness.

        First call: writes AGENTS.md, runs opencode (new session).
        Subsequent calls: runs opencode --continue (same session).

        Returns (skill_bundle, outputs) where outputs is {relative_path: content}.
        """
        if self._workspace is None and sandbox._workspace:
            self._workspace = sandbox._workspace / "app"
        if self._workspace is None:
            raise RuntimeError("Sandbox workspace not available")

        if self._harness is None:
            self._harness = OpenCodeHarness(
                model=_model_from_client(self.client),
                max_turns=self.max_turns,
                timeout=3600,
            )
            agents_md = _build_agents_md(
                instruction=instruction,
                available_skills=available_skills,
            )
            print(f"  {C.cyan('GENERATOR')} | Writing AGENTS.md + starting opencode...")
            result = self._harness.run(
                instruction=instruction,
                workspace=self._workspace,
                system_prompt=agents_md,
            )
        else:
            print(f"  {C.cyan('GENERATOR')} | Continuing opencode session...")
            result = self._harness.run(
                instruction=instruction,
                workspace=self._workspace,
                feedback=feedback,
            )

        self._last_result = result

        print(
            f"  {C.cyan('GENERATOR')} | opencode done: {result.turn_count} turns, "
            f"completed={result.completed}, tokens={result.token_usage}"
        )

        outputs = _collect_outputs(sandbox)

        if result.outputs:
            for relpath, content in result.outputs.items():
                if relpath not in outputs:
                    outputs[relpath] = content

        print(f"  {C.cyan('GENERATOR')} | {len(outputs)} output files: {list(outputs.keys())[:5]}")

        skill = _read_skill_from_sandbox(sandbox)
        if skill:
            print(f"  {C.cyan('GENERATOR')} | Skill '{skill.name}' found")
        else:
            print(f"  {C.cyan('GENERATOR')} | No evo-* skill found — fallback")
            skill = SkillBundle(name="evo-task", skillell="# Fallback skill\n")

        return skill, outputs

    def append_oracle_signal(self, score: float) -> None:
        """Pass oracle binary pass/fail signal to generator context (Alg. 1 line 29).

        Paper: C ← C ⊕ 1[R(i)<1] — only the opaque binary bit, no score or test content.
        This prevents the Generator from overfitting to the held-out ground-truth tests.
        """
        if score >= 1.0:
            msg = "Ground-truth oracle: PASS."
        else:
            msg = "Ground-truth oracle: FAIL. Escalate and improve."
        logger.info("Oracle signal: %s", msg)

    def context_usage_ratio(self) -> float:
        return 0.0

    def get_turn_summary(self) -> str:
        if self._last_result:
            return (
                f"OpenCodeHarness: {self._last_result.turn_count} turns, "
                f"completed={self._last_result.completed}, "
                f"tokens={self._last_result.token_usage}\n"
                f"{self._last_result.summary[:500]}"
            )
        return "OpenCodeHarness: not yet executed"

    @property
    def persisted_context(self) -> bool:
        return self._harness is not None and self._harness._session_id is not None


def _model_from_client(client: LLMClient) -> str:
    """Convert LLMClient model name to opencode provider/model format."""
    model = getattr(client, "model", "deepseek-chat")
    if "deepseek" in model:
        return f"deepseek/{model}"
    elif "gpt" in model or "openai" in model:
        return f"openai/{model}"
    elif "claude" in model or "anthropic" in model:
        return f"anthropic/{model}"
    return f"deepseek/{model}"


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
    ec2, out2, _ = sandbox.run(f"find {scripts_dir} -type f -not -name '*.pyc' 2>/dev/null", timeout=5)
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
