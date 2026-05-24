from __future__ import annotations

import json
import re

from repository.skill import SkillBundle, parse_skill_from_text, serialize_skill
from utils.llm.client import LLMClient
from utils.llm.types import Message


class SkillGenerator:
    """Skill Generator (§3.3 Eq.7).

    Maintains a persistent conversation context C and iteratively
    generates/refines skill bundles S based on verification feedback F.

    The generator operates in a structured loop:
      1. Receive task instruction I and initial context (S_meta).
      2. Explore the environment (list files, check tools).
      3. Generate/update a skill bundle S.
      4. Execute the skill to produce outputs.
      5. If verifier reports failures, refine the skill.
    """

    def __init__(self, client: LLMClient, system_prompt: str, meta_skill: str = ""):
        self.client = client
        self.system_prompt = system_prompt
        self.meta_skill = meta_skill
        self.context: list[Message] = []
        self._token_count: int = 0

    def init_context(self, instruction: str, previous_skill: SkillBundle | None = None) -> None:
        """Initialize the conversation context C.

        C is initialized as (I, S_meta) per the paper (§3.3).
        If previous_skill is provided, it's included for version tracking.
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

    def generate(self, instruction: str, feedback: str | None = None) -> tuple[str, dict | None]:
        """Generate or refine a skill, returning raw LLM response.

        Args:
            instruction: Task instruction I.
            feedback: Failure diagnostic F(i,j) from Surrogate Verifier.
                None on initial generation.

        Returns:
            (raw_response_text, parsed_json_or_None).
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
            system=self.system_prompt,
            temperature=0.0,
            max_tokens=4096,
        )

        self.context.append(response.message)
        self._token_count += response.usage.input_tokens + response.usage.output_tokens

        text = response.message.content or ""
        parsed = _try_parse_json(text)

        return text, parsed

    def extract_skill(self, response_text: str) -> SkillBundle | None:
        """Extract a SkillBundle from the generator's response.

        The response may contain SKILL.md content delimited by markdown
        code fences, or the full skill structure.
        """
        skillell_content = _extract_code_block(response_text, "markdown")
        if not skillell_content:
            skillell_content = _extract_code_block(response_text, "md")
        if not skillell_content:
            skillell_content = _extract_yaml_block(response_text)

        if skillell_content:
            skill = parse_skill_from_text(skillell_content)
            if skill.name == "unnamed":
                skill.metadata["name"] = "evo-task"
            return skill
        return None

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
