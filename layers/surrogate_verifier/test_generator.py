from __future__ import annotations

from utils.llm.client import LLMClient
from utils.llm.types import Message

TEST_GEN_SYSTEM_PROMPT = """\
You are a test engineer generating deterministic Python test assertions for a task.
You receive:
1. The task instruction (requirements, expected outputs, format specs).
2. The agent's output files (file paths and contents).

Generate Python test assertions that check:
- Output file existence
- File format correctness (valid JSON, correct structure, required fields)
- Content correctness (values match expected ranges or patterns)
- Edge cases mentioned in the instruction

RULES:
- Tests MUST be deterministic (no randomness, no external API calls)
- Tests MUST be self-contained (use only standard library + assertions)
- Each assertion should be a single Python function with assert statements
- Tests verify OUTCOMES only, never check which tools were used

Output format: one Python function per assertion, as a list of code strings.
"""

TEST_ESCALATE_PROMPT = """\
All your current tests passed, but a ground-truth oracle test (whose contents
you cannot see) still found issues. This means your tests are not comprehensive
enough.

Your task: GENERATE ADDITIONAL, MORE RIGOROUS TEST ASSERTIONS.

Consider:
- Tighter numerical tolerances
- Additional edge cases from the instruction
- Boundary conditions
- Output format edge cases
- Hidden assumptions in the instruction

Generate NEW test assertions that go beyond your current suite. Keep all
existing tests and add these new ones. Respond with a JSON list of new
assertion code strings.
"""


class TestGenerator:
    """Generates deterministic test assertions e_k for the verifier test suite V.

    Tests are derived from the task instruction I and output file artifacts,
    without access to ground-truth test content or skill internals.
    """

    def __init__(self, client: LLMClient):
        self.client = client

    def generate(
        self,
        instruction: str,
        outputs: dict[str, str],
        existing_suite: list[str] | None = None,
    ) -> list[str]:
        """Generate initial test assertions.

        Args:
            instruction: Task instruction I.
            outputs: Output file artifacts x(i).
            existing_suite: Previous test suite V(j), if any.

        Returns:
            List of test assertion strings (Python code snippets).
        """
        outputs_summary = _format_outputs(outputs)

        prompt = f"""\
Task instruction:
{instruction}

Agent output files:
{outputs_summary}

Generate 3-10 deterministic Python test assertions for this task.
Each assertion should be a function body (no def line needed, just the assert statements).

Respond with a JSON list of strings, each a Python assertion code block.
IMPORTANT: Use RELATIVE file paths (strip leading /). Files are in the current directory.
Example:
["assert os.path.exists('root/output.json'), 'Output file missing'", ...]
"""

        response = self.client.send(
            messages=[Message.user(prompt)],
            system=TEST_GEN_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2048,
        )

        tests = _parse_test_list(response.message.content or "")
        return tests if tests else _generate_fallback_tests(instruction, outputs)

    def escalate(
        self,
        instruction: str,
        outputs: dict[str, str],
        existing_suite: list[str],
    ) -> list[str]:
        """Escalate test suite with additional, more rigorous assertions.

        Args:
            instruction: Task instruction I.
            outputs: Output file artifacts x(i).
            existing_suite: Previous test suite V(j).

        Returns:
            Updated test suite V(j+1) with additional tests.
        """
        outputs_summary = _format_outputs(outputs)
        existing_summary = "\n".join(
            f"- {t[:100]}..." for t in existing_suite
        )

        prompt = f"""\
Task instruction:
{instruction}

Agent output files:
{outputs_summary}

Current test suite (all passed):
{existing_summary}

""" + TEST_ESCALATE_PROMPT

        response = self.client.send(
            messages=[Message.user(prompt)],
            system=TEST_GEN_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=2048,
        )

        new_tests = _parse_test_list(response.message.content or "")
        return existing_suite + new_tests


def _format_outputs(outputs: dict[str, str]) -> str:
    if not outputs:
        return "No output files found."

    parts: list[str] = []
    for path, content in list(outputs.items())[:20]:
        truncated = content[:1000]
        parts.append(f"### {path}\n```\n{truncated}\n```")
    return "\n\n".join(parts)


def _parse_test_list(text: str) -> list[str]:
    import json
    import re

    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass

    return _extract_python_blocks(text)


def _extract_python_blocks(text: str) -> list[str]:
    import re

    blocks = re.findall(r"```(?:python)?\s*\n([\s\S]*?)```", text)
    return [b.strip() for b in blocks if b.strip()]


def _generate_fallback_tests(instruction: str, outputs: dict[str, str]) -> list[str]:
    """Generate basic tests when LLM parsing fails."""
    tests: list[str] = []
    for path in outputs:
        relpath = path.lstrip("/")
        tests.append(f"assert os.path.exists('{relpath}'), 'Output file {relpath} missing'")
    if not tests:
        tests.append("assert False, 'No output files produced by the agent'")
    return tests
