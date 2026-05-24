from __future__ import annotations

import logging

from layers.surrogate_verifier.feedback import Feedback, PerAssertionResult
from layers.surrogate_verifier.test_generator import TestGenerator
from layers.surrogate_verifier.test_runner import TestRunner
from utils.llm.client import LLMClient
from utils.llm.types import Message

logger = logging.getLogger(__name__)

VERIFIER_SYSTEM_PROMPT = """\
You are an independent test engineer. Your task is to verify agent outputs against
a task specification. You operate in a separate LLM session — you have NO access
to the agent's internal reasoning, code, or skill content.

You receive:
1. The task instruction (what output files should exist, format requirements,
    correctness criteria).
2. The actual output files produced by the agent.

Your job:
1. Generate deterministic test assertions (Python code) that can be executed
    to verify the outputs.
2. When tests fail, provide structured failure diagnostics including:
    - Root-cause analysis (why the output is wrong)
    - Actionable revision suggestions for the agent

RULES for root-cause analysis:
- Only cite causes directly visible in the test failure output.
- NEVER speculate about: file permissions, race conditions,
  sandbox/symlink behavior, network timeouts, or any cause
  you cannot directly observe in the test results.
- If you cannot determine the root cause from visible evidence,
  say "Cannot determine from test results" and focus on
  describing what correct output WOULD look like.
- Revision suggestions should describe WHAT output is expected,
  not HOW the agent should produce it.
"""


class SurrogateVerifier:
    """Surrogate Verifier (§3.3 Eq.4, Eq.8).

    Operates in a completely independent LLM session πV_θ, observing only
    the task instruction I and output files x(i). It:
      1. Generates/refines a proxy test suite V.
      2. Computes the surrogate reward R̃ (Eq.4).
      3. Produces structured failure diagnostics F when R̃ < 1.
      4. Escalates tests when R̃=1 but oracle reports failure.
    """

    def __init__(self, client: LLMClient):
        self.client = client
        self.test_generator = TestGenerator(client)
        self.test_runner = TestRunner()

    def evaluate(
        self,
        instruction: str,
        outputs: dict[str, str],
        test_suite: list[str] | None = None,
    ) -> tuple[float, Feedback | None, list[str]]:
        """Run the verifier test suite V(j) against outputs x(i).

        If no test suite provided, generates one from scratch.

        Returns:
            R̃ — surrogate reward ∈ [0, 1] (Eq.4).
            F  — failure diagnostic if R̃ < 1, else None.
            test_suite — the test suite used (persisted for next round).
        """
        if not test_suite:
            test_suite = self.test_generator.generate(instruction, outputs)
            logger.info("VERIFIER: generated %d tests:", len(test_suite))
            for i, t in enumerate(test_suite):
                logger.info("  TEST[%d]: %s", i, t[:200])
            print(f"  VERIFIER  | {len(test_suite)} tests generated")

        r_tilde, results = self.test_runner.run(test_suite, outputs)
        logger.info("Test run: R̃=%.2f, %d/%d passed", r_tilde,
                     sum(1 for r in results if r.passed), len(results))

        has_failure = any(not r.passed for r in results)
        if has_failure:
            feedback = self._generate_feedback(instruction, outputs, test_suite, results)
            return r_tilde, feedback, test_suite

        return r_tilde, None, test_suite

    def escalate(
        self,
        instruction: str,
        outputs: dict[str, str],
        test_suite: list[str],
    ) -> list[str]:
        """Escalate test suite V(j) → V(j+1) (Eq.8).

        Triggered when R̃=1 but oracle reports failure (R<1).
        Generates more diverse, comprehensive, and challenging test cases.

        The escalation prompt tells the verifier that all its tests passed
        but the ground-truth oracle still found issues, so it must strengthen
        its tests without access to the hidden oracle content.
        """
        return self.test_generator.escalate(instruction, outputs, test_suite)

    def _generate_feedback(
        self,
        instruction: str,
        outputs: dict[str, str],
        test_suite: list[str],
        results: list[PerAssertionResult],
    ) -> Feedback:
        """Generate structured failure diagnostic F(i,j).

        Uses the LLM to analyze failures and produce root-cause analysis
        and actionable revision suggestions.
        """
        failed = [r for r in results if not r.passed]
        failed_summary = "\n".join(
            f"- Test: {r.assertion[:120]}...\n  Error: {r.error}"
            for r in failed
        )

        outputs_summary = "\n".join(
            f"File: {path}\nContent:\n{content[:500]}\n"
            for path, content in list(outputs.items())[:10]
        )

        prompt = f"""\
Task instruction:
{instruction}

Agent output files:
{outputs_summary}

Failed test assertions:
{failed_summary}

Analyze these failures. Provide:
1. Root-cause analysis: why did the agent's output fail these tests?
   CRITICAL: Only cite evidence directly visible in the test failures.
   NEVER speculate about file permissions, symlinks, sandbox issues,
   network/API problems, or race conditions. If you cannot determine
   the cause, say "Cannot determine from test results" and describe
   what correct output should contain.
2. Actionable revision suggestions: what should the agent change to pass?
   Describe WHAT output is expected, not HOW to produce it.

Respond in JSON format:
{{"root_cause_analysis": "...", "revision_suggestions": ["...", "..."]}}
"""

        response = self.client.send(
            messages=[Message.user(prompt)],
            system=VERIFIER_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2048,
        )

        analysis = _try_parse_json(response.message.content or "")
        root_cause = analysis.get("root_cause_analysis", "") if analysis else ""
        suggestions = analysis.get("revision_suggestions", []) if analysis else []

        return Feedback(
            overall_pass=False,
            surrogate_reward=sum(1 for r in results if r.passed) / max(len(results), 1),
            assertion_results=results,
            root_cause_analysis=root_cause,
            revision_suggestions=suggestions,
        )


def _try_parse_json(text: str) -> dict | None:
    import json
    import re

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
