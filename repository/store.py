from __future__ import annotations

import json
import time
from pathlib import Path

from repository.skill import SkillBundle, serialize_skill


class ArtifactStore:
    """Persistent storage for evolution artifacts: skills, traces, logs.

    Directory layout:
        {root}/
            skills/
                {task_name}/
                    SKILL.md
                    scripts/
            traces/
                {task_name}/
                    round_0.json
                    round_1.json
                    ...
            logs/
                {task_name}.log
            results/
                results.json
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.traces_dir = self.root / "traces"
        self.logs_dir = self.root / "logs"
        self.results_dir = self.root / "results"

        for d in [self.skills_dir, self.traces_dir, self.logs_dir, self.results_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save_skill(self, skill: SkillBundle, task_name: str) -> Path:
        """Save an evolved skill for a task.

        Writes to {root}/skills/{task_name}/SKILL.md.
        """
        task_skill_dir = self.skills_dir / task_name
        task_skill_dir.mkdir(parents=True, exist_ok=True)

        (task_skill_dir / "SKILL.md").write_text(serialize_skill(skill))

        scripts_dir = task_skill_dir / "scripts"
        if skill.scripts:
            scripts_dir.mkdir(exist_ok=True)
            for filename, content in skill.scripts.items():
                file_path = scripts_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)

        return task_skill_dir

    def load_skill(self, task_name: str) -> SkillBundle | None:
        """Load a previously saved skill for a task."""
        from repository.skill import parse_skill_dir

        skill_dir = self.skills_dir / task_name
        if not (skill_dir / "SKILL.md").exists():
            return None
        return parse_skill_dir(skill_dir)

    def save_trace(self, trace_data: dict, task_name: str, round_num: int) -> Path:
        """Save a single evolution round trace.

        Each trace captures:
            - skill_version: current skill state
            - verifier_tests: current test suite V
            - surrogate_reward: R̃ value
            - oracle_reward: R value (if oracle was called)
            - feedback: failure diagnostic (if any)
            - context_usage: context window utilization
        """
        task_trace_dir = self.traces_dir / task_name
        task_trace_dir.mkdir(parents=True, exist_ok=True)

        trace_path = task_trace_dir / f"round_{round_num}.json"
        trace_path.write_text(json.dumps(trace_data, indent=2, default=str))
        return trace_path

    def save_results(self, results: list[dict], filename: str = "results.json") -> Path:
        """Save evaluation results as JSON."""
        path = self.results_dir / filename
        path.write_text(json.dumps(results, indent=2, default=str))
        return path

    def write_log(self, task_name: str, message: str) -> None:
        """Append a log message for a task."""
        log_path = self.logs_dir / f"{task_name}.log"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
