from __future__ import annotations

import statistics
from collections import defaultdict


def compute_pass_rate(results: list[dict]) -> tuple[float, float]:
    """Compute pass rate (%) and standard deviation from evaluation results.

    Each result dict must have:
        reward: float (0.0 or 1.0) or converged: bool

    Returns (mean_pct, std_pct).
    """
    rewards = [
        r.get("reward", 1.0 if r.get("converged") else 0.0)
        for r in results
    ]
    if not rewards:
        return 0.0, 0.0

    mean = statistics.mean(rewards) * 100
    std = statistics.stdev(rewards) * 100 if len(rewards) > 1 else 0.0
    return mean, std


def per_domain_pass_rate(results: list[dict]) -> dict[str, tuple[float, int]]:
    """Compute pass rate broken down by domain.

    Each result dict must have a 'category' field.
    Returns dict of domain → (pass_rate_pct, task_count).
    """
    domain_results: dict[str, list[float]] = defaultdict(list)
    for r in results:
        category = r.get("category", r.get("domain", "unknown"))
        reward = r.get("reward", 1.0 if r.get("converged") else 0.0)
        domain_results[category].append(reward)

    output: dict[str, tuple[float, int]] = {}
    for domain, rewards in sorted(domain_results.items()):
        rate = statistics.mean(rewards) * 100
        output[domain] = (rate, len(rewards))
    return output


def compute_delta(results_with: list[dict], results_without: list[dict]) -> float:
    """Compute the delta (pass rate improvement) between two result sets."""
    with_rate, _ = compute_pass_rate(results_with)
    without_rate, _ = compute_pass_rate(results_without)
    return with_rate - without_rate
