from __future__ import annotations

import json
from pathlib import Path

from engine.evolution import EvolutionMetrics
from eval.metrics import compute_pass_rate


class Reporter:
    """Aggregates and reports evaluation results.

    Generates summary tables, per-task breakdowns, and domain-level
    analysis matching paper Figures 4–6 and Tables A1–B1.
    """

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def report_summary(self, metrics_list: list[EvolutionMetrics]) -> str:
        """Generate a summary report from evolution metrics."""
        results = [
            {
                "task": m.task_name,
                "converged": m.converged,
                "reward": m.final_reward,
                "rounds": m.rounds,
                "oracle_calls": m.oracle_calls,
                "surrogate_retries": m.surrogate_retries,
                "error": m.error,
            }
            for m in metrics_list
        ]

        pass_rate, std = compute_pass_rate(results)
        converged = sum(1 for m in metrics_list if m.converged)
        total = len(metrics_list)

        avg_rounds = sum(m.rounds for m in metrics_list) / max(total, 1)
        avg_oracle = sum(m.oracle_calls for m in metrics_list) / max(total, 1)
        avg_surrogate = sum(m.surrogate_retries for m in metrics_list) / max(total, 1)

        lines = [
            "=" * 60,
            "CoEvoSkills Evolution Report",
            "=" * 60,
            f"Pass rate:         {pass_rate:.1f}% ± {std:.1f}",
            f"Tasks converged:   {converged}/{total}",
            f"Avg rounds/task:   {avg_rounds:.1f}",
            f"Avg oracle calls:  {avg_oracle:.1f}",
            f"Avg surrogate:     {avg_surrogate:.1f}",
            "=" * 60,
        ]

        errors = [m for m in metrics_list if m.error]
        if errors:
            lines.append("\nErrors:")
            for m in errors:
                lines.append(f"  {m.task_name}: {m.error}")

        return "\n".join(lines)

    def save_json(self, metrics_list: list[EvolutionMetrics], filename: str = "results.json") -> Path:
        """Save results as JSON."""
        results = [
            {
                "task": m.task_name,
                "converged": m.converged,
                "reward": m.final_reward,
                "best_reward": m.best_reward,
                "rounds": m.rounds,
                "oracle_calls": m.oracle_calls,
                "surrogate_retries": m.surrogate_retries,
                "history": m.history,
                "error": m.error,
            }
            for m in metrics_list
        ]
        path = self.output_dir / filename
        path.write_text(json.dumps(results, indent=2, default=str))
        return path

    def print_per_task(self, metrics_list: list[EvolutionMetrics]) -> None:
        """Print per-task pass/fail table."""
        header = f"{'Task':<40} {'Status':<10} {'Rounds':<8} {'Oracle':<8}"
        print(header)
        print("-" * len(header))
        for m in metrics_list:
            status = "PASS" if m.converged else ("ERR" if m.error else "FAIL")
            print(f"{m.task_name:<40} {status:<10} {m.rounds:<8} {m.oracle_calls:<8}")
