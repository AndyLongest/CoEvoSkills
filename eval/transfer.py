from __future__ import annotations

from pathlib import Path

from repository.task import load_all_tasks


def evaluate_transfer(
    skills_dir: str | Path,
    target_models: list[str],
    tasks_dir: str | Path,
) -> dict:
    """Cross-model transfer evaluation (§4.4).

    Takes skills evolved by a source model and evaluates them on
    target models to measure skill portability.

    For each target model:
      1. Load pre-installed skills.
      2. Run oracle evaluation on all tasks.
      3. Compare with no-skill baseline.

    Returns dict of model → (with_skills_pct, no_skill_pct, delta).
    """
    skills_dir = Path(skills_dir)
    results: dict = {}

    tasks = load_all_tasks(tasks_dir)

    for model in target_models:
        no_skill_rewards: list[float] = []
        with_skill_rewards: list[float] = []

        for task in tasks:
            # No-skill baseline: run oracle without any installed skills
            ns_reward = _run_oracle_eval(task, None, model)
            no_skill_rewards.append(ns_reward)

            # With-skills: run oracle with evolved skill installed
            skill_path = skills_dir / task.name / "SKILL.md"
            if skill_path.exists():
                ws_reward = _run_oracle_eval(task, skill_path, model)
                with_skill_rewards.append(ws_reward)

        ns_pct = sum(no_skill_rewards) / max(len(no_skill_rewards), 1) * 100
        ws_pct = sum(with_skill_rewards) / max(len(with_skill_rewards), 1) * 100
        results[model] = (ws_pct, ns_pct, ws_pct - ns_pct)

    return results


def _run_oracle_eval(task, skill_path: Path | None, model: str) -> float:
    """Run oracle evaluation for a single task-model pair.

    In a full implementation, this would:
    1. Set up the sandbox with the model-specific agent harness.
    2. Install the skill if provided.
    3. Run the agent.
    4. Execute the verifier tests.

    Returns 0.0 or 1.0.
    """
    return 0.0
