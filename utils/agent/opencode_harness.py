from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.colors import C

logger = logging.getLogger(__name__)


@dataclass
class OpenCodeResult:
    """Structured result from an opencode harness run."""

    completed: bool = False
    outputs: dict[str, str] = field(default_factory=dict)
    turn_count: int = 0
    token_usage: int = 0
    session_id: str = ""
    summary: str = ""


EVOLUTION_AGENTS_MD = """\
# CoEvoSkills Evolution Agent

You solve command-line tasks in a Linux sandbox. Create reusable skills and execute them.

## Workflow

1. Read input data from /app/environment/data/ and /data/.
2. Read pre-installed skills from /app/environment/skills/. Each has SKILL.md + scripts/.
3. Read the skill-creator SKILL.md to understand how to create proper skills:
   /app/environment/skills/skill-creator/SKILL.md (if exists)
4. Create an evo-* skill at /app/environment/skills/evo-NAME/ with SKILL.md and scripts/.
   The SKILL.md must follow the skill-creator format with name, description, and usage.
5. Write /root/run.py that imports skill functions:
       import sys; sys.path.insert(0, '/app/environment/skills/evo-NAME/scripts')
       from utils import func
6. Run: python3 /root/run.py. Output files go to /root/.

## Rules
- No sudo.
- Import functions, don't copy-paste.
- Self-contained skills — internalize all domain knowledge in SKILL.md + scripts/.
- Write a summary file at /root/evolution_summary.md when done.
"""


class OpenCodeHarness:
    """Agent harness using opencode CLI as the execution engine.

    Replaces the JSON-protocol AgentLoop. Uses opencode's native tool set
    (bash, read, write, edit, glob, grep, task, webfetch) and session
    management for multi-round evolution.

    opencode reads AGENTS.md from the workspace directory as its system
    instructions, so we write task-specific instructions before each run.
    """

    def __init__(
        self,
        model: str = "deepseek/deepseek-v4-pro",
        max_turns: int = 20,
        timeout: int = 3600,
    ):
        self.model = model
        self.max_turns = max_turns
        self.timeout = timeout
        self._session_id: str | None = None

    def run(
        self,
        instruction: str,
        workspace: Path,
        system_prompt: str | None = None,
        feedback: str | None = None,
    ) -> OpenCodeResult:
        """Run opencode in the workspace directory.

        Writes AGENTS.md with task instructions before each run.
        On subsequent calls with the same harness instance, uses --session
        --continue to maintain conversation context.

        Args:
            instruction: Task instruction for the agent.
            workspace: Working directory (Docker volume mount path).
            system_prompt: Custom AGENTS.md content (overrides default).
            feedback: Feedback from verifier/oracle (appended as user message).

        Returns:
            OpenCodeResult with completion status and collected outputs.
        """
        self._write_agents_md(workspace, instruction, system_prompt)

        args: list[str] = [
            "opencode",
            "run",
            instruction,
            "--model",
            self.model,
            "--agent",
            "coevo-evolution",
            "--dir",
            str(workspace),
            "--format",
            "json",
        ]

        if self._session_id:
            args += ["--session", self._session_id, "--continue"]

        if feedback:
            args.append(feedback)

        print(f"  {C.dim('OPENCODE')}  | Starting harness (session={self._session_id or 'new'})...")

        proc = None
        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "OPENCODE_NO_COLOR": "1"},
            )

            if proc.stdout is None:
                return OpenCodeResult(completed=False, summary="No stdout from opencode")

            result = self._stream_events(proc)
            proc.wait(timeout=self.timeout)

            if self._session_id is None and result.session_id:
                self._session_id = result.session_id

            return result

        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                proc.wait()
            logger.warning("OpenCode timeout after %ds", self.timeout)
            return OpenCodeResult(completed=False, summary="OpenCode timed out")

        except Exception as e:
            logger.error("OpenCode harness error: %s", e)
            return OpenCodeResult(completed=False, summary=str(e))

    def _stream_events(self, proc: subprocess.Popen) -> OpenCodeResult:
        """Read JSON lines from opencode stdout and build the result."""
        result = OpenCodeResult()
        turn_starts = 0
        token_total = 0

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "step_start":
                turn_starts += 1
                sid = event.get("sessionID", "")
                if sid and not result.session_id:
                    result.session_id = sid

            elif etype == "step_finish":
                part = event.get("part", {})
                reason = part.get("reason", "")
                tokens = part.get("tokens", {})
                token_total = tokens.get("total", token_total)

                if reason == "stop":
                    result.completed = True

            elif etype == "text":
                part = event.get("part", {})
                text = part.get("text", "")
                if text:
                    result.summary = (result.summary + text)[:2000]

            elif etype == "tool_use":
                part = event.get("part", {})
                tool = part.get("tool", "")
                state = part.get("state", {})
                if tool in ("write", "edit"):
                    inp = state.get("input", {})
                    filepath = inp.get("filePath", "")
                    content = inp.get("content", "")
                    if filepath and content:
                        relpath = filepath.lstrip("/")
                        result.outputs[relpath] = content

        result.turn_count = turn_starts
        result.token_usage = token_total

        if not result.completed:
            result.summary += f"\n[exited after {turn_starts} turns, token_usage={token_total}]"

        return result

    def _write_agents_md(
        self,
        workspace: Path,
        instruction: str,
        system_prompt: str | None,
    ) -> None:
        """Write AGENTS.md with task-specific instructions to the workspace."""
        content = system_prompt if system_prompt else EVOLUTION_AGENTS_MD

        agenda = f"\n\n## Task\n\n{instruction}\n"

        agents_path = workspace / "AGENTS.md"
        agents_path.parent.mkdir(parents=True, exist_ok=True)
        agents_path.write_text(content + agenda)

    def context_usage_ratio(self) -> float:
        return 0.0  # opencode manages context natively

    def get_turn_summary(self) -> str:
        return f"OpenCodeHarness (model={self.model}, session={self._session_id})"
