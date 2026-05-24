from __future__ import annotations

import logging

from repository.skill import SkillBundle
from utils.agent.prompts import EXECUTION_AGENT_SYSTEM_PROMPT
from utils.executor.sandbox import Sandbox
from utils.llm.client import LLMClient

logger = logging.getLogger(__name__)


class Executor:
    """Skill Executor Φ(S, E) — Algorithm 1 lines 7, 15.

    Executes a skill bundle S in environment E and produces output artifacts x(i).
    This is NOT an LLM call — it writes the skill files to the sandbox and runs
    an agent session with execution-only prompt.
    """

    def __init__(self, client: LLMClient, max_turns: int = 10, beta: float = 0.7):
        self.client = client
        self.max_turns = max_turns
        self.beta = beta

    def execute(
        self,
        skill: SkillBundle,
        sandbox: Sandbox,
        instruction: str,
        skill_loader=None,
    ) -> dict[str, str]:
        """Execute skill S in environment E, returning output files.

        Args:
            skill: The skill bundle to execute.
            sandbox: Initialized sandbox with task environment already prepared.
            instruction: Task instruction for the agent.
            skill_loader: Optional callback to load skills by name.

        Returns:
            Dict of {relative_filepath: content} produced by the agent.
        """
        from utils.agent.loop import AgentLoop

        # Write skill into sandbox
        self._install_skill(sandbox, skill)

        # Run execution-only agent
        prompt = EXECUTION_AGENT_SYSTEM_PROMPT.replace(
            "{skills_block}", self._build_skills_block(skill)
        )
        agent = AgentLoop(
            client=self.client,
            sandbox=sandbox,
            system_prompt=prompt,
            max_turns=self.max_turns,
            beta=self.beta,
        )
        if skill_loader:
            agent.set_skill_loader(skill_loader)
        agent.init_context(instruction)
        agent.run_loop(instruction)

        # Collect outputs
        outputs: dict[str, str] = {}
        for search_dir in ["/root", "/app"]:
            ec, stdout, _ = sandbox.run(
                f"find {search_dir} -maxdepth 1 -type f 2>/dev/null", timeout=10
            )
            if ec == 0 and stdout:
                for line in stdout.strip().split("\n"):
                    abspath = line.strip()
                    if abspath and "progress.md" not in abspath:
                        content = sandbox.read_file(abspath)
                        if content:
                            relpath = abspath.lstrip("/")
                            outputs[relpath] = content
        if not outputs:
            ec, out, _ = sandbox.run("find . -maxdepth 1 -type f 2>/dev/null", timeout=5)
            if ec == 0 and out:
                for line in out.strip().split("\n"):
                    path = line.strip()
                    if path and "progress.md" not in path:
                        content = sandbox.read_file(path)
                        if content:
                            outputs[path.replace("./", "")] = content

        return outputs

    def _install_skill(self, sandbox: Sandbox, skill: SkillBundle) -> None:
        """Write skill files into the sandbox."""
        base = f"/app/environment/skills/{skill.name}"
        sandbox.write_file(f"{base}/SKILL.md", skill.skillell)
        for script_name, content in skill.scripts.items():
            sandbox.write_file(f"{base}/{script_name}", content)
        logger.info("EXECUTOR: installed skill '%s' (%d scripts)",
                     skill.name, len(skill.scripts))

    def _build_skills_block(self, skill: SkillBundle) -> str:
        """Build a skills block with the actual skill content for the agent prompt.

        Includes the full SKILL.md content so the agent knows exactly what
        functions are available and how to import them — matching the paper's
        Φ(S, E) design where πθ executes with full knowledge of the skill.
        """
        lines = [
            f"=== Skill: {skill.name} ===",
            skill.skillell,
            "",
            "### Script files:",
        ]
        for name in skill.scripts:
            lines.append(f"- {name}")
        return "\n".join(lines)
