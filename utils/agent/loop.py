from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable

from utils.agent.prompts import EVOLUTION_AGENT_SYSTEM_PROMPT
from utils.executor.sandbox import Sandbox
from utils.llm.client import LLMClient
from utils.llm.types import Message

logger = logging.getLogger(__name__)


class AgentLoop:
    """Paper-style agent interaction loop (§3.3, Appendix F.1).

    Implements the turn-based protocol where:
      1. Agent produces JSON with {analysis, plan, commands, task_complete}
      2. Host executes commands via sandbox
      3. Host feeds terminal output back to agent
      4. Agent can request skill loading via "load_skill" field

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

    def set_skill_loader(self, loader: Callable[[str], str | None]) -> None:
        """Register a callback for loading skill content by name.

        When the agent requests {"load_skill": "skill-name"}, this callback
        is invoked. It should return the SKILL.md content as a string, or
        None if the skill is not found.
        """
        self._skill_loader = loader

    def init_context(
        self,
        instruction: str,
        meta_skill: str = "",
        env_files: str = "",
        installed_tools: str = "",
    ) -> None:
        """Initialize the conversation context C(0) = (I, S_meta).

        Maps to the paper: C ← (I, Smeta), then S(0) ~ πθ(· | C).
        Subsequent calls to run_loop() continue from this context.

        Pre-injecting environment info (file tree, installed tools) eliminates
        the LLM's discovery turns (P1/P1b), equivalent to having run ls/find/pip list.
        """
        self._turn_count = 0
        self._messages = []
        self._estimated_tokens = 0

        parts: list[str] = []

        if env_files:
            parts.append(f"=== Environment Files (already discovered) ===\n{env_files}")

        if installed_tools:
            parts.append(f"=== Installed Tools & Libraries ===\n{installed_tools}")

        if meta_skill:
            parts.append(f"{meta_skill}")

        parts.append(f"Task Description:\n{instruction}")

        parts.append(
            "\nNOTE: Environment discovery (P1/P1b) has already been completed. "
            "The files and tools above have been verified. Start from P2 (create/update skill)."
        )

        content = "\n\n---\n\n".join(parts)
        self._messages.append(Message.user(content))
        self._estimated_tokens += _estimate_tokens(content) + _estimate_tokens(self.system_prompt)

    def append(self, message: str) -> None:
        """Append a message to the conversation context."""
        self._messages.append(Message.user(message))
        self._estimated_tokens += _estimate_tokens(message)

    def context_usage_ratio(self) -> float:
        """Return the proportion of the LLM context window currently in use."""
        return min(self._estimated_tokens / self.max_context_tokens, 1.0)

    def run_loop(self, instruction: str) -> tuple[bool, str]:
        """Run the agent execution loop starting from current context.

        Uses the existing self._messages. Call init_context() first.
        Resets turn counter so each evolution round gets a fresh budget.
        """
        self._turn_count = 0
        prompt = self.system_prompt.replace(
            "{skills_block}", self._build_skills_block(),
        )

        while self._turn_count < self.max_turns:
            if self.context_usage_ratio() > self.beta:
                logger.warning(
                    "Context budget exceeded: %.1f%% > β=%.1f, stopping agent",
                    self.context_usage_ratio() * 100, self.beta * 100,
                )
                return False, self._conversation_summary()

            logger.info("Agent turn %d/%d", self._turn_count + 1, self.max_turns)
            print(f"  GENERATOR | Turn {self._turn_count + 1}/{self.max_turns}...")
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
                self._messages.append(Message.user(
                    f"ERROR: Response must be valid JSON with 'commands' field.\n\n"
                    f"Expected format:\n"
                    f'{{"analysis": "...", "plan": "...", '
                    f'"commands": [{{"keystrokes": "...", "duration": 1.0}}], '
                    f'"task_complete": false}}\n\n'
                    f"Your response was:\n---\n{preview}\n---\n"
                    f"Re-read the response format and try again."
                ))
                self._turn_count += 1
                continue

            if "load_skill" in parsed:
                skill_content = self._load_skill(parsed["load_skill"])
                if skill_content:
                    self._messages.append(Message.user(
                        f"Skill '{parsed['load_skill']}' loaded:\n\n{skill_content}"
                    ))
                else:
                    self._messages.append(Message.user(
                        f"Skill '{parsed['load_skill']}' not found."
                    ))

            commands = parsed.get("commands", [])
            if commands:
                terminal_output = self._execute_commands(commands)
                self._messages.append(Message.user(terminal_output))

            if parsed.get("task_complete", False):
                return True, self._conversation_summary()

            self._turn_count += 1
            logger.info("TURN %d/%d done, resp=%d chars, cmds=%d, ctx=%.1f%%",
                self._turn_count, self.max_turns,
                len(text), len(commands),
                self.context_usage_ratio() * 100)

        return False, self._conversation_summary()

    def run(self, instruction: str, skill_name: str | None = None) -> tuple[bool, str]:
        """Convenience: init context then run loop."""
        self.init_context(instruction)
        return self.run_loop(instruction)

    def _parse_response(self, text: str) -> dict | None:
        """Parse the agent's JSON response, handling markdown code fences."""
        text = text.strip()

        # Try direct JSON parse
        try:
            parsed = json.loads(text)
            logger.info("PARSE: direct JSON ok (%d keys)", len(parsed))
            return parsed
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code fence
        match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
        if match:
            try:
                parsed = json.loads(match.group(1).strip())
                logger.info("PARSE: extracted from markdown fence (%d keys)", len(parsed))
                return parsed
            except json.JSONDecodeError:
                pass

        # Try extracting JSON object with regex
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

    def _execute_commands(self, commands: list[dict]) -> str:
        """Execute a list of command objects and return the terminal output.

        Each command: {"keystrokes": "ls -la\\n", "duration": 0.1}
        Special keystrokes: C-c (Ctrl+C), C-d (Ctrl+D)
        """
        outputs: list[str] = []
        for cmd in commands:
            keystrokes = cmd.get("keystrokes", "")
            duration = cmd.get("duration", 1.0)

            if not keystrokes:
                time.sleep(duration)
                continue

            logger.info("CMD: %s", keystrokes[:200].replace("\n", "\\n"))
            cmd_preview = keystrokes[:200].replace("\n", "\\n")
            print(f"    $ {cmd_preview}")

            parsed = self._parse_keystrokes(keystrokes)
            for pcmd, ptimeout in parsed:
                exit_code, stdout, stderr = self.sandbox.run(
                    pcmd, timeout=int(ptimeout) or self.command_timeout
                )
                output = stdout
                if exit_code != 0:
                    output += f"\n[EXIT {exit_code}] {stderr}" if stderr else f"\n[EXIT {exit_code}]"
                outputs.append(f"$ {pcmd}\n{output.strip()}")

        return "=== Terminal Output ===\n" + "\n\n".join(outputs)

    def _parse_keystrokes(self, keystrokes: str) -> list[tuple[str, int]]:
        """Parse keystrokes into individual commands.

        Newlines (\n) separate commands. Special sequences:
        - C-c → send SIGINT to running process
        - C-d → send EOF
        """
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
        """Load a skill by name using the registered loader callback."""
        if self._skill_loader:
            return self._skill_loader(name)
        return f"No skill loader registered. Skill '{name}' cannot be loaded."

    def _build_skills_block(self) -> str:
        """Build a skills availability block for the system prompt."""
        return "Use the skill system to load and create reusable skill packages."

    def _conversation_summary(self) -> str:
        """Return a summary of the conversation for logging."""
        parts: list[str] = []
        for msg in self._messages:
            role = msg.role.upper()
            content = (msg.content or "")[:500]
            parts.append(f"[{role}]\n{content}")
        return "\n\n".join(parts)


def run_agent(
    client: LLMClient,
    sandbox: Sandbox,
    instruction: str,
    skill_name: str | None = None,
    skill_loader: Callable[[str], str | None] | None = None,
    max_turns: int = 50,
) -> tuple[bool, str]:
    """Convenience function: run a single agent execution.

    Args:
        client: LLM client for the agent.
        sandbox: Sandbox for command execution.
        instruction: Task instruction.
        skill_name: Pre-installed skill name.
        skill_loader: Callback to load skill content.
        max_turns: Maximum agent turns.

    Returns:
        (task_complete: bool, conversation_summary: str).
    """
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
