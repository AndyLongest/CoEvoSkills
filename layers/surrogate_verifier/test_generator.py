from __future__ import annotations

from utils.llm.client import LLMClient
from utils.llm.types import Message

TEST_GEN_SYSTEM_PROMPT = """\
You are a test engineer generating deterministic Python test assertions for a task.
You receive:
1. The task instruction (requirements, expected outputs, format specs).
2. The agent's output files (file paths and contents), including any input data files
    that were used by the agent (e.g., test.bib). Use these input files to independently
    compute what the CORRECT output should be.

Generate Python test assertions that check:
- Output file existence
- File format correctness (valid JSON, correct structure, required fields)
- Content correctness: independently derive expected values from the input files
  and assert that the agent's output matches. Do NOT just check format — compute
  the correct answer from input data and compare with the agent's output.
- Edge cases mentioned in the instruction

RULES:
- Tests MUST be deterministic (no randomness, no external API calls)
- CRITICAL: Each assertion MUST be EXACTLY ONE Python statement.
  - NO for loops, while, if/else, try/except, or function definitions
  - NO multiple statements joined with ;
  - Import statements, variable assignments, and asserts are each ONE statement
  - Syntax errors cause immediate compilation failure, wasting limited test slots
- Tests verify OUTCOMES only, never check which tools were used
- CRITICAL: ALL file paths MUST be relative. Use 'root/answer.json', NOT '/root/answer.json'.
  Absolute paths will cause PermissionError on the test runner host.
- CRITICAL: Read input files to independently compute expected values, then compare
  against the agent's output. This is the ONLY way to catch content errors.

Output format: a JSON list of assertion code strings. Each string is one Python statement.
"""

TEST_ESCALATE_PROMPT = """\
All your current tests passed, but a ground-truth oracle test (whose contents
you cannot see) still found issues. This means your tests are not comprehensive
enough — they may be checking format but missing content errors.

Your task: GENERATE ADDITIONAL, MORE RIGOROUS TEST ASSERTIONS.

Consider:
- READING INPUT FILES: Your existing tests may only check output format.
  ADD tests that read the input data (e.g., test.bib) and independently compute
  what the correct answer should be, then compare against the agent's output.
- Tighter tolerances and edge cases
- Missing content checks your current suite might have missed
- Boundary conditions and hidden assumptions in the instruction
- Testing specific values derived from input data, not just generic format checks

Generate NEW test assertions that go beyond your current suite. Keep all
existing tests and add these new ones. Respond with a JSON list of new
assertion code strings.

FORMAT: Each assertion must be EXACTLY ONE Python statement — either
an assignment or a single assert. NO for loops, if/else, try/except,
semicolons, or function definitions. Import statements are OK.

IMPORTANT: The test code is executed via exec() in a namespace that already provides
os, open, json, re, Path. You do NOT need to import these. For any other modules,
include your own import statement.
All assertions share the same namespace — variables defined in one assertion
are available in subsequent assertions.

CRITICAL — FILE PATHS: ALL file paths MUST be relative. Tests run in a temporary
directory where output files are placed. Use 'root/answer.json', NOT '/root/answer.json'.
Absolute paths cause PermissionError.
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

Agent output files (including input data used by the agent):
{outputs_summary}

Generate 5-15 deterministic Python test assertions for this task.
Use the input files to independently compute expected answers, then compare with output.

APPROACH:
1. First, write setup assertions to load data: import libraries, read input files, parse JSON.
2. Then, write computation assertions to derive expected values from input data.
3. Finally, write comparison assertions to check agent output against expected values.
All assertions share the same namespace.

EXAMPLES of CONTENT-driven tests (read input files, compute expected, compare):
["import bibtexparser",
 "data = json.load(open('root/answer.json'))",
 "with open('root/test.bib') as f: bib_db = bibtexparser.loads(f.read())",
 "suspicious_dois = ['10.1234/', '10.5678/']",
 "expected_titles = sorted(e.get('title','') for e in bib_db.entries if any(e.get('doi','').startswith(p) for p in suspicious_dois))",
 "assert data['fake_citations'] == expected_titles, f'Expected {{expected_titles}}, got {{data[\"fake_citations\"]}}'"]

FORMAT: Each item must be EXACTLY ONE Python statement — an import, assignment, or single assert.
NO for loops, if/else, try/except, ;, or function definitions.

IMPORTANT: The test code is executed via exec() in a namespace that already provides
os, open, json, re, Path. You do NOT need to import these. For any other modules,
include your own import statement.
All assertions share the same namespace — variables defined in one assertion
are available in subsequent assertions.

CRITICAL — FILE PATHS: ALL file paths MUST be relative. The test runs in a temporary
directory where output files are placed. Use 'root/answer.json', NOT '/root/answer.json'.
Absolute paths starting with / will cause PermissionError and fail every test.

Respond with a JSON list of strings.
"""

        response = self.client.send(
            messages=[Message.user(prompt)],
            system=TEST_GEN_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=4096,
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
            max_tokens=4096,
        )

        new_tests = _parse_test_list(response.message.content or "")
        return existing_suite + new_tests


def _format_outputs(outputs: dict[str, str]) -> str:
    if not outputs:
        return "No output files found."

    parts: list[str] = []
    for path, content in list(outputs.items())[:20]:
        truncated = content[:5000]
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
