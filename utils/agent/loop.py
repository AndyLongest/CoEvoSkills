from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable

from utils.agent.prompts import EVOLUTION_AGENT_SYSTEM_PROMPT
from utils.colors import C
from utils.executor.sandbox import Sandbox
from utils.llm.client import LLMClient
from utils.llm.types import Message

logger = logging.getLogger(__name__)


class AgentLoop:
    """Paper-style agent interaction loop (§3.3, Appendix F.1).

    Implements the turn-based protocol where:
      1. Agent produces JSON with {analysis, plan, commands, task_complete}
      2. Host executes commands via sandbox
      3. Host feeds terminal output + workspace changes back to agent
      4. Agent can request skill loading via "load_skill" field
      5. Agent can delegate subtasks to sub-agents via "delegate" field

    This is the execution agent used by both the Skill Generator (evolution
    phase) and the Oracle (evaluation phase).
    """

    def __init__(
        self,
        client: LLMClient,
        sandbox: Sandbox,
        system_prompt: str = EVOLUTION_AGENT_SYSTEM_PROMPT,
        max_turns: int = 5,
        command_timeout: int = 60,
        beta: float = 0.7,
        max_context_tokens: int = 128000,
    ):
        self.client = client
        self.sandbox = sandbox
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.command_timeout = command_timeout
        self.beta = beta
        self.max_context_tokens = max_context_tokens
        self._turn_count = 0
        self._messages: list[Message] = []
        self._skill_loader: Callable[[str], str | None] | None = None
        self._estimated_tokens: int = 0
        self._sub_agents_disabled: bool = False
        self._turn_history: list[dict] = []

    def set_skill_loader(self, loader: Callable[[str], str | None]) -> None:
        self._skill_loader = loader

    def init_context(
        self,
        instruction: str,
        meta_skill: str = "",
        env_files: str = "",
        installed_tools: str = "",
        available_skills: dict[str, str] | None = None,
    ) -> None:
        """Initialize the conversation context C(0) = (I, S_meta).

        Args:
            available_skills: {skill_name: description} for {skills_block} substitution.
        """
        self._available_skills = available_skills or {}
        self._turn_count = 0
        self._messages = []
        self._estimated_tokens = 0

        parts: list[str] = []

        parts.append(
            "=== ENVIRONMENT (pre-discovered) ===\n"
            "The file tree and tool list below are already confirmed. "
            "Do NOT re-run ls/find/pip list. "
            "If /app/environment/doc/ exists, you still need to READ those files."
        )

        if env_files:
            parts.append(f"File tree:\n{env_files}")

        if installed_tools:
            parts.append(f"=== Installed Tools & Libraries ===\n{installed_tools}")

        if meta_skill:
            parts.append(f"{meta_skill}")

        parts.append(f"Task Description:\n{instruction}")

        parts.append(
            "\nNOTE: Environment discovery (P1) has already been completed. "
            "The file tree and tool list above are the confirmed environment state. "
            "Do NOT run ls/find/pip list again. Start directly from P2 (create/update skill)."
        )

        content = "\n\n---\n\n".join(parts)
        self._messages.append(Message.user(content))
        self._estimated_tokens += _estimate_tokens(content) + _estimate_tokens(self.system_prompt)

    def append(self, message: str) -> None:
        self._messages.append(Message.user(message))
        self._estimated_tokens += _estimate_tokens(message)

    def context_usage_ratio(self) -> float:
        return min(self._estimated_tokens / self.max_context_tokens, 1.0)

    def run_loop(self, instruction: str) -> tuple[bool, str]:
        """Run the agent execution loop starting from current context."""
        self._turn_count = 0
        self._turn_history = []
        prompt = self.system_prompt.replace(
            "{skills_block}",
            self._build_skills_block(),
        )

        while self._turn_count < self.max_turns:
            if self.context_usage_ratio() > self.beta:
                logger.warning(
                    "Context budget exceeded: %.1f%% > β=%.1f, stopping agent",
                    self.context_usage_ratio() * 100,
                    self.beta * 100,
                )
                self._dump_turn_history()
                return False, self._conversation_summary()

            logger.info("Agent turn %d/%d", self._turn_count + 1, self.max_turns)
            print(f"  {C.dim('GENERATOR')} | Turn {self._turn_count + 1}/{self.max_turns}...")
            response = self.client.send(
                messages=list(self._messages),
                system=prompt,
                temperature=0.0,
                max_tokens=8192,
            )
            self._messages.append(response.message)
            text = response.message.content or ""
            self._estimated_tokens += _estimate_tokens(text)

            parsed = self._parse_response(text)

            if parsed is None:
                preview = text[:1000]
                logger.warning("PARSE FAIL turn %d: %s", self._turn_count + 1, text[:200])
                print(f"  {C.red('GENERATOR')} | Turn {self._turn_count + 1} PARSE FAIL: {text[:150]}...")
                self._turn_history.append(
                    {
                        "turn": self._turn_count + 1,
                        "parse": "FAIL",
                        "preview": text[:100],
                    }
                )
                self._messages.append(
                    Message.user(
                        f"ERROR: Response must be valid JSON with 'commands' field.\n\n"
                        f"Expected format:\n"
                        f'{{"analysis": "...", "plan": "...", '
                        f'"commands": [{{"keystrokes": "...", "duration": 1.0}}], '
                        f'"task_complete": false}}\n\n'
                        f"Your response was:\n---\n{preview}\n---\n"
                        f"Re-read the response format and try again."
                    )
                )
                self._turn_count += 1
                continue

            load_skill = parsed.get("load_skill", "")
            cmds = parsed.get("commands", [])
            task_done = parsed.get("task_complete", False)
            cmd_preview = " ".join(c.get("keystrokes", "")[:60] for c in cmds[:3]) if cmds else "(none)"
            logger.info(
                "TURN %d: load=%s cmds=%d task_done=%s preview=%s",
                self._turn_count + 1,
                load_skill,
                len(cmds),
                task_done,
                cmd_preview,
            )
            print(
                f"  {C.dim('GENERATOR')} | Turn {self._turn_count + 1} OK: cmds={len(cmds)} load={'Y' if load_skill else 'N'} done={task_done} [{cmd_preview}]"
            )

            self._turn_history.append(
                {
                    "turn": self._turn_count + 1,
                    "parse": "ok",
                    "cmds": len(cmds),
                    "load_skill": load_skill or "N",
                    "task_complete": task_done,
                    "preview": cmd_preview,
                }
            )

            if "load_skill" in parsed:
                skill_content = self._load_skill(parsed["load_skill"])
                if skill_content:
                    self._messages.append(Message.user(f"Skill '{parsed['load_skill']}' loaded:\n\n{skill_content}"))
                else:
                    self._messages.append(Message.user(f"Skill '{parsed['load_skill']}' not found."))

            if "delegate" in parsed and not self._sub_agents_disabled:
                delegate = parsed["delegate"]
                result = self._handle_delegate(delegate)
                if result:
                    self._messages.append(Message.user(result))
                if parsed.get("task_complete", False):
                    return True, self._conversation_summary()
                self._turn_count += 1
                continue

            commands = parsed.get("commands", [])
            before_snapshot = self._snapshot_files() if commands else set()

            if commands:
                terminal_output = self._execute_commands(commands, before_snapshot)
                self._messages.append(Message.user(terminal_output))

            if parsed.get("task_complete", False):
                self._turn_history.append(
                    {
                        "turn": self._turn_count + 1,
                        "parse": "ok",
                        "cmds": len(commands),
                        "load_skill": load_skill or "N",
                        "task_complete": True,
                        "preview": cmd_preview,
                    }
                )
                self._dump_turn_history()
                return True, self._conversation_summary()

            self._turn_count += 1
            logger.info(
                "TURN %d/%d done, resp=%d chars, cmds=%d, ctx=%.1f%%",
                self._turn_count,
                self.max_turns,
                len(text),
                len(commands),
                self.context_usage_ratio() * 100,
            )

        self._dump_turn_history()
        return False, self._conversation_summary()

    def run(self, instruction: str, skill_name: str | None = None) -> tuple[bool, str]:
        """Convenience: init context then run loop."""
        self.init_context(instruction)
        return self.run_loop(instruction)

    def _parse_response(self, text: str) -> dict | None:
        """Parse the agent's JSON response, handling markdown code fences."""
        text = text.strip()

        try:
            parsed = json.loads(text)
            logger.info("PARSE: direct JSON ok (%d keys)", len(parsed))
            return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if match:
            try:
                parsed = json.loads(match.group(1).strip())
                logger.info("PARSE: extracted from markdown fence (%d keys)", len(parsed))
                return parsed
            except json.JSONDecodeError:
                pass

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                parsed = json.loads(match.group())
                logger.info("PARSE: regex JSON object (%d keys)", len(parsed))
                return parsed
            except json.JSONDecodeError:
                pass

        logger.warning("PARSE: failed, text preview=%s", text[:300])
        return None

    # ─────────────────────────────────────────────
    # Command execution
    # ─────────────────────────────────────────────

    def _execute_commands(self, commands: list[dict], before_snapshot: set[str] = None) -> str:
        """Execute a list of command objects and return enhanced terminal output.

        Adds diagnostic context on failures and reports file changes after execution.
        """
        outputs: list[str] = []
        had_failure = False

        for cmd in commands:
            keystrokes = cmd.get("keystrokes", "")
            duration = cmd.get("duration", 1.0)

            if not keystrokes:
                time.sleep(duration)
                continue

            logger.info("CMD: %s", keystrokes[:200].replace("\n", "\\n"))

            parsed = self._parse_keystrokes(keystrokes)
            for pcmd, ptimeout in parsed:
                try:
                    exit_code, stdout, stderr = self.sandbox.run(pcmd, timeout=int(ptimeout) or self.command_timeout)
                except Exception as e:
                    exit_code = 1
                    stdout = ""
                    stderr = str(e)

                output = stdout
                if exit_code != 0:
                    had_failure = True
                    output += f"\n[EXIT {exit_code}] {stderr}" if stderr else f"\n[EXIT {exit_code}]"
                outputs.append(f"$ {pcmd}\n{output.strip()}")

        result = "=== Terminal Output ===\n" + "\n\n".join(outputs)

        if had_failure:
            result += "\n\n" + self._build_failure_diagnostics()

        if before_snapshot is not None:
            diff = self._compute_diff(before_snapshot)
            if diff:
                result += "\n\n" + diff

        return result

    def _build_failure_diagnostics(self) -> str:
        """Build diagnostic context when a command fails.

        Provides file system state that helps the LLM understand why the
        command failed, mimicking Claude-Code's automatic context enrichment.
        """
        parts: list[str] = ["=== Diagnostic Context (auto-generated) ==="]
        recent_files = self._get_recent_output_files()

        if recent_files:
            parts.append("Recently modified files:")
            parts.append(recent_files)

        pip_summary = self._get_pip_summary()
        if pip_summary:
            parts.append("Installed packages (pip list --format=freeze):")
            parts.append(pip_summary)

        return "\n".join(parts)

    # ─────────────────────────────────────────────
    # Workspace state tracking (Claude-Code parity)
    # ─────────────────────────────────────────────

    def _snapshot_files(self) -> set[str]:
        """Capture the current state of /root and /app file trees."""
        files: set[str] = set()
        for search_dir in ["/root", "/app"]:
            ec, stdout, _ = self.sandbox.run(
                f"find {search_dir} -maxdepth 3 \\( -type f -o -type l \\) "
                f"-not -path '*/.venv/*' -not -path '*/__pycache__/*' "
                f"-not -path '*/site-packages/*' 2>/dev/null",
                timeout=15,
            )
            if ec == 0 and stdout:
                for line in stdout.strip().split("\n"):
                    if line.strip():
                        files.add(line.strip())
        return files

    def _compute_diff(self, before: set[str]) -> str:
        """Compute workspace diff: what files were created, modified, or deleted."""
        after = self._snapshot_files()
        created = [f for f in after - before if f not in before]
        deleted = [f for f in before - after if f not in after]
        modified = []

        for f in before & after:
            ec, stdout, _ = self.sandbox.run(
                f"stat -c '%Y' '{f}' 2>/dev/null",
                timeout=5,
            )
            if ec == 0 and stdout.strip():
                try:
                    mtime = int(stdout.strip())
                    if mtime > int(time.time()) - 300:
                        modified.append(f)
                except (ValueError, OSError):
                    pass

        lines: list[str] = []
        if created:
            lines.append(f"Created ({len(created)} files):\n  " + "\n  ".join(sorted(created)[:20]))
        if modified:
            lines.append(f"Modified ({len(modified)} files):\n  " + "\n  ".join(sorted(modified)[:20]))
        if deleted:
            lines.append(f"Deleted ({len(deleted)} files):\n  " + "\n  ".join(sorted(deleted)[:20]))

        if lines:
            return "=== Workspace Changes ===\n" + "\n".join(lines)
        return ""

    def _get_recent_output_files(self) -> str:
        """List recently modified files in /root and /app for diagnostics."""
        ec, stdout, _ = self.sandbox.run(
            "find /root /app -maxdepth 2 \\( -type f -o -type l \\) "
            "-not -path '*/.venv/*' -not -path '*/__pycache__/*' "
            "-not -path '*/site-packages/*' -newer /root/progress.md 2>/dev/null | head -30",
            timeout=10,
        )
        if ec == 0 and stdout.strip():
            return stdout.strip()
        return ""

    def _get_pip_summary(self) -> str:
        """Get installed pip packages for ImportError diagnosis."""
        ec, stdout, _ = self.sandbox.run(
            "pip list --format=freeze 2>/dev/null | head -40",
            timeout=10,
        )
        if ec == 0 and stdout.strip():
            return stdout.strip()
        return ""

    # ─────────────────────────────────────────────
    # Sub-agent delegation (Claude-Code subtask decomposition)
    # ─────────────────────────────────────────────

    def _handle_delegate(self, delegate: dict) -> str | None:
        """Handle a sub-agent delegation request.

        The agent can delegate a focused subtask to a sub-AgentLoop with
        its own instruction and budget. Results are returned inline.

        JSON format: {"delegate": {"instruction": "...", "max_turns": 5}}
        """
        sub_instruction = delegate.get("instruction", "")
        if not sub_instruction:
            return "ERROR: delegate missing 'instruction' field."

        sub_max_turns = min(delegate.get("max_turns", 3), 5)
        logger.info("DELEGATE: running sub-agent (max %d turns)", sub_max_turns)

        from utils.agent.prompts import EXECUTE_ONLY_SYSTEM_PROMPT

        sub_agent = AgentLoop(
            client=self.client,
            sandbox=self.sandbox,
            system_prompt=EXECUTE_ONLY_SYSTEM_PROMPT,
            max_turns=sub_max_turns,
            command_timeout=self.command_timeout,
            beta=self.beta,
            max_context_tokens=self.max_context_tokens // 2,
        )
        sub_agent._sub_agents_disabled = True
        if self._skill_loader:
            sub_agent.set_skill_loader(self._skill_loader)

        print(f"  {C.dim('DELEGATE')}  | Sub-agent: {sub_instruction[:80]}...")
        completed, summary = sub_agent.run(sub_instruction)
        sub_agent_success = "completed" if completed else "incomplete"
        print(f"  {C.dim('DELEGATE')}  | Sub-agent {sub_agent_success} ({sub_max_turns} turns)")

        return (
            f"=== Sub-agent Result ({sub_agent_success}) ===\n"
            f"Instruction: {sub_instruction}\n"
            f"Summary:\n{summary[:2000]}"
        )

    # ─────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────

    def _parse_keystrokes(self, keystrokes: str) -> list[tuple[str, int]]:
        """Parse keystrokes into individual commands."""
        lines = keystrokes.split("\\n")
        commands: list[tuple[str, int]] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line == "C-c":
                commands.append(("pkill -INT -P $$ 2>/dev/null || true", 1))
            elif line == "C-d":
                continue
            else:
                commands.append((line, self.command_timeout))

        return commands

    def _load_skill(self, name: str) -> str | None:
        if self._skill_loader:
            return self._skill_loader(name)
        return f"No skill loader registered. Skill '{name}' cannot be loaded."

    def _build_skills_block(self) -> str:
        skills = getattr(self, "_available_skills", {})
        if not skills:
            return "No pre-installed skills available. You MUST create an evo-* skill from scratch."

        lines = [
            "The following skills are pre-installed in the sandbox and can be loaded:",
            "",
        ]
        for name, desc in skills.items():
            lines.append(f"- **{name}**: {desc}")
            lines.append(f'  Load: {{"load_skill": "{name}"}}')
            lines.append("")

        lines += [
            "Important notes:",
            f'- Load skill-creator FIRST before creating skills: {{"load_skill": "skill-creator"}}',
            f"- To use a loaded skill, write a script in /root/ that imports its scripts/ directory:",
            f"    import sys; sys.path.insert(0, '/app/environment/skills/EVO-SKILLNAME/scripts')",
            f"    from utils import function_name",
            f"- Write task OUTPUT files to /root/ (e.g., /root/result.json)",
        ]
        return "\n".join(lines)

    def _conversation_summary(self) -> str:
        parts: list[str] = []
        for msg in self._messages:
            role = msg.role.upper()
            content = (msg.content or "")[:500]
            parts.append(f"[{role}]\n{content}")
        return "\n\n".join(parts)

    def _dump_turn_history(self) -> str:
        """Log and print a turn-by-turn summary for debugging.

        Returns the summary string for callers to persist (e.g., store.write_log).
        """
        if not self._turn_history:
            msg = "Turn history: no turns recorded"
            print(f"  {C.dim('GENERATOR')} | {msg}")
            logger.info(msg)
            return msg

        total = len(self._turn_history)
        okay = sum(1 for t in self._turn_history if t["parse"] == "ok")
        fails = total - okay
        done_turns = sum(1 for t in self._turn_history if t.get("task_complete", False))
        loaded = sum(1 for t in self._turn_history if t.get("load_skill", "N") != "N")
        with_cmds = sum(1 for t in self._turn_history if t.get("cmds", 0) > 0)

        lines = [
            f"AgentLoop done: {total} turns, OK={okay}, PARSE_FAIL={fails}, "
            f"cmds_executed={with_cmds}, skill_loaded={loaded}, completed={done_turns}",
        ]

        for t in self._turn_history:
            if t["parse"] == "FAIL":
                lines.append(f"  Turn {t['turn']}: PARSE FAIL — {t.get('preview', '')[:120]}")
            else:
                lines.append(
                    f"  Turn {t['turn']}: cmds={t.get('cmds', 0)} load={t.get('load_skill', 'N')} "
                    f"done={t.get('task_complete', False)} [{t.get('preview', '')[:80]}]"
                )

        summary = "\n".join(lines)
        logger.info(summary)
        print(f"  {C.cyan('GENERATOR')} | Turn history: {summary}")
        return summary

    def get_turn_summary(self) -> str:
        """Return the turn history summary without printing."""
        return self._dump_turn_history()


def run_agent(
    client: LLMClient,
    sandbox: Sandbox,
    instruction: str,
    skill_name: str | None = None,
    skill_loader: Callable[[str], str | None] | None = None,
    max_turns: int = 50,
) -> tuple[bool, str]:
    """Convenience function: run a single agent execution."""
    loop = AgentLoop(
        client=client,
        sandbox=sandbox,
        system_prompt=EVOLUTION_AGENT_SYSTEM_PROMPT,
        max_turns=max_turns,
    )
    if skill_loader:
        loop.set_skill_loader(skill_loader)
    return loop.run(instruction, skill_name)


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate (~4 chars per token for English text)."""
    return max(len(text) // 4, 1)
