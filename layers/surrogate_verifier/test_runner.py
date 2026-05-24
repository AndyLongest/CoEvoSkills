from __future__ import annotations

import logging
import os
import tempfile
import traceback

from layers.surrogate_verifier.feedback import PerAssertionResult

logger = logging.getLogger(__name__)


class TestRunner:
    """Executes deterministic test assertions against output artifacts.

    Computes the surrogate reward R̃ = (1/|V|) * Σ 1[e_k(x)] (Eq.4).

    Each assertion is a Python expression or statement that evaluates to
    a boolean. Assertions are executed in a temporary directory where
    the output files are materialized.
    """

    def run(self, tests: list[str], outputs: dict[str, str]) -> tuple[float, list[PerAssertionResult]]:
        """Execute all assertions and compute R̃.

        Args:
            tests: List of assertion strings (Python code).
            outputs: Dict of {file_path: file_content} from the agent.

        Returns:
            R̃ — proportion of passing tests ∈ [0, 1].
            results — per-assertion (pass/fail, error message).
        """
        if not tests:
            return 0.0, []

        with tempfile.TemporaryDirectory(prefix="coevo_test_") as tmp:
            self._materialize_outputs(tmp, outputs)
            results = self._execute_tests(tests, tmp)

        passed_count = sum(1 for r in results if r.passed)
        r_tilde = passed_count / len(results) if results else 0.0
        return r_tilde, results

    def _materialize_outputs(self, tmp_dir: str, outputs: dict[str, str]) -> None:
        """Write output files to a temporary directory for test execution."""
        for filepath, content in outputs.items():
            clean_path = filepath.lstrip("/")
            full_path = os.path.join(tmp_dir, clean_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

    def _execute_tests(self, tests: list[str], tmp_dir: str) -> list[PerAssertionResult]:
        """Execute each assertion and collect pass/fail results."""
        results: list[PerAssertionResult] = []

        for i, test_code in enumerate(tests):
            result = self._run_single_assertion(test_code, tmp_dir, i)
            results.append(result)

        return results

    def _run_single_assertion(self, test_code: str, tmp_dir: str, index: int) -> PerAssertionResult:
        """Execute a single assertion in an isolated namespace."""
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_dir)

            namespace: dict = {
                "os": os,
                "open": open,
                "__builtins__": __builtins__,
            }

            try:
                exec(test_code, namespace)
                logger.info("ASSERT[%d]: PASS — %s", index, test_code[:120])
                print(f"  VERIFIER  |   ✓ [{index}] {test_code[:100]}")
                return PerAssertionResult(
                    assertion=test_code,
                    passed=True,
                )
            except AssertionError as e:
                logger.info("ASSERT[%d]: FAIL — %s", index, test_code[:120])
                print(f"  VERIFIER  |   ✗ [{index}] {test_code[:100]}")
                return PerAssertionResult(
                    assertion=test_code,
                    passed=False,
                    error=str(e) or f"Assertion {index} failed",
                )
            except Exception as e:
                logger.info("ASSERT[%d]: ERROR — %s", index, test_code[:120])
                print(f"  VERIFIER  |   ! [{index}] {test_code[:100]}")
                return PerAssertionResult(
                    assertion=test_code,
                    passed=False,
                    error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                )
        finally:
            os.chdir(orig_cwd)
