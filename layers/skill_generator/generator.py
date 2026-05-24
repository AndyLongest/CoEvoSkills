from __future__ import annotations

import json
import logging
import re

from repository.skill import SkillBundle, parse_skill_from_text, serialize_skill
from utils.agent.prompts import GENERATOR_SYSTEM_PROMPT
from utils.llm.client import LLMClient
from utils.llm.types import Message

logger = logging.getLogger(__name__)


class SkillGenerator:
    """Skill Generator πθ (§3.3 Eq.7).

    Maintains a persistent conversation context C and iteratively
    generates/refines skill bundles S based on verification feedback F.

    Per Algorithm 1:
      S(i)  ∼ πθ(·|C)            initial generation
      S(i+1) ∼ πθ(·|C ⊕ F)       refinement with feedback
    """

    def __init__(self, client: LLMClient, meta_skill: str = ""):
        self.client = client
        self.meta_skill = meta_skill
        self.context: list[Message] = []
        self._token_count: int = 0

    def init_context(self, instruction: str, previous_skill: SkillBundle | None = None,
                     env_context: str = "") -> None:
        """Initialize the conversation context C.

        C is initialized as (I, S_meta) per the paper (§3.3).
        If previous_skill is provided, it's included for version tracking.
        If env_context is provided, environment files and dependencies are injected.
        """
        self.context = []

        task_block = f"Task Description:\n{instruction}"
        if self.meta_skill:
            task_block = f"{self.meta_skill}\n\n---\n\n{task_block}"

        self.context.append(Message.user(task_block))

        if previous_skill:
            self.context.append(Message.user(
                "Previous evolved skill (load and improve):\n\n"
                f"{serialize_skill(previous_skill)}"
            ))

        if env_context:
            self.context.append(Message.user(
                f"Environment files and available context for this task:\n\n{env_context}"
            ))

    def generate(self, instruction: str, feedback: str | None = None) -> SkillBundle | None:
        """Generate or refine a skill bundle.

        Args:
            instruction: Task instruction I.
            feedback: Failure diagnostic F(i,j) from Surrogate Verifier.
                None on initial generation.

        Returns:
            SkillBundle or None if generation fails.
        """
        if not self.context:
            self.init_context(instruction)

        if feedback:
            self.context.append(Message.user(
                f"Host verifier found failures in the previous attempt. "
                f"Fix your skill to address these issues:\n\n{feedback}"
            ))

        messages = list(self.context)
        response = self.client.send(
            messages=messages,
            system=GENERATOR_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=8192,
        )

        self.context.append(response.message)
        self._token_count += response.usage.input_tokens + response.usage.output_tokens

        text = response.message.content or ""
        logger.info("GENERATOR: response %d chars", len(text))

        return self.extract_skill(text)

    def extract_skill(self, response_text: str) -> SkillBundle | None:
        """Extract a SkillBundle from the generator's response.

        The response is a markdown document with YAML frontmatter (SKILL.md)
        and optional Python scripts in code blocks with filename=scripts/xxx.py.
        """
        skillell_content = _extract_yaml_block(response_text)
        if not skillell_content:
            logger.warning("GENERATOR: no YAML frontmatter found in response")
            return None

        skill = parse_skill_from_text(skillell_content)
        if skill.name == "unnamed":
            skill.metadata["name"] = "evo-task"

        # Extract scripts from filename=scripts/xxx.py code blocks
        scripts = _extract_script_blocks(response_text)
        if scripts:
            skill.scripts = scripts
            logger.info("GENERATOR: extracted %d script files", len(scripts))

        return skill

    def append_feedback(self, feedback: str) -> None:
        """Append failure diagnostic to the conversation context C (Eq.7)."""
        self.context.append(Message.user(feedback))

    def append_oracle_signal(self, passed: bool) -> None:
        """Append oracle pass/fail bit to context (no test content)."""
        signal = "Ground-truth oracle: ALL TESTS PASSED." if passed else "Ground-truth oracle: TESTS FAILED. Escalate and improve."
        self.context.append(Message.user(signal))

    def context_usage_ratio(self) -> float:
        """Return estimated context window usage proportion."""
        return min(self._token_count / 100000, 1.0)

    @property
    def conversation_history(self) -> str:
        """Return the full conversation as a readable string."""
        parts: list[str] = []
        for msg in self.context:
            role = msg.role.upper()
            content = msg.content or ""
            parts.append(f"[{role}]\n{content}")
        return "\n\n".join(parts)


def _try_parse_json(text: str) -> dict | None:
    """Try to extract and parse a JSON object from text."""
    text = text.strip()

    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _extract_code_block(text: str, lang: str) -> str | None:
    """Extract content from a markdown code fence with the given language."""
    pattern = rf"```{lang}\s*\n([\s\S]*?)```"
    matches = re.findall(pattern, text)
    if matches:
        return matches[0].strip()
    return None


def _extract_yaml_block(text: str) -> str | None:
    """Extract content that starts with YAML frontmatter (--- ... ---)."""
    match = re.search(r"---\s*\n([\s\S]*?)---\s*\n([\s\S]*)", text)
    if match:
        return f"---\n{match.group(1)}\n---\n{match.group(2)}"
    return None


def _extract_script_blocks(text: str) -> dict[str, str]:
    """Extract script files from filename=scripts/xxx.py code blocks.

    The generator response uses this format:
    ```python filename=scripts/utils.py
    def func():
        pass
    ```

    Returns dict of {relative_path: content}.
    """
    scripts: dict[str, str] = {}
    pattern = r"```(?:python)?\s+filename=([^\s]+)\s*\n([\s\S]*?)```"
    for match in re.finditer(pattern, text):
        filepath = match.group(1).strip()
        content = match.group(2).strip()
        if filepath and content:
            scripts[filepath] = content
    return scripts
