"""Run the CoEvoSkills evolution on SkillsBench tasks.

Usage:
    python scripts/evolve.py
    python scripts/evolve.py --tasks exoplanet-detection-period
    python scripts/evolve.py --model deepseek-v4-pro
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.evolution import EvolutionMetrics, run_evolution
from engine.scheduler import Scheduler
from eval.reporter import Reporter
from layers.oracle.oracle import Oracle
from layers.surrogate_verifier.verifier import SurrogateVerifier
from repository.store import ArtifactStore
from repository.task import load_all_tasks, load_task
from utils.config import Config, load_config
from utils.llm.anthropic import AnthropicClient
from utils.llm.client import LLMClient
from utils.llm.deepseek import DeepSeekClient
from utils.llm.openai import OpenAIClient
from utils.logger import setup_logger


def _make_client(config: Config) -> LLMClient:
    """Create an LLM client based on config or explicit provider."""
    model = config.llm_model
    model_lower = model.lower()
    if "deepseek" in model_lower:
        return DeepSeekClient(model=model)
    elif "gpt" in model_lower or "openai" in model_lower:
        return OpenAIClient(model=model)
    elif "claude" in model_lower or "anthropic" in model_lower:
        return AnthropicClient(model=model)
    else:
        return DeepSeekClient(model=model)


def main():
    parser = argparse.ArgumentParser(description="CoEvoSkills skill evolution")
    parser.add_argument("--config", default="configs/default.yaml", type=Path, help="Config file path")
    parser.add_argument("--tasks", default="all", help="Task name or 'all'")
    parser.add_argument("--model", default=None, help="Override LLM model")
    parser.add_argument("--provider", default=None, choices=["anthropic", "openai", "deepseek"], help="LLM provider")
    parser.add_argument("--output", default="./output", type=Path, help="Output directory")
    parser.add_argument("--benchmark", default="./skillsbench", type=Path, help="SkillsBench root")
    parser.add_argument("--parallel", default=None, type=int, help="Override parallel workers")
    parser.add_argument("--n", default=None, type=int, help="Override evolution N (max oracle interventions)")
    parser.add_argument("--m", default=None, type=int, help="Override evolution M (max surrogate retries)")
    parser.add_argument(
        "--partial-credit", action="store_true", help="Enable partial credit (Oracle returns passed/total ratio)"
    )
    args = parser.parse_args()

    logger = setup_logger("coevo-evolve")
    logger.info("CoEvoSkills evolution started")

    config = load_config(args.config) if Path(args.config).exists() else Config()

    if args.model:
        config.llm_model = args.model
    if args.n is not None:
        config.evolution.n = args.n
    if args.m is not None:
        config.evolution.m = args.m
    if args.partial_credit:
        config.oracle.partial_credit = True

    output_dir = Path(args.output)
    store = ArtifactStore(output_dir)
    skill_dir = output_dir / "skills"
    skill_dir.mkdir(parents=True, exist_ok=True)

    client = _make_client(config)
    verifier_client = _make_client(config)

    meta_skill = _load_meta_skill()

    if args.tasks == "all":
        tasks = load_all_tasks(args.benchmark)
        logger.info(f"Loaded {len(tasks)} tasks")
    else:
        # Try as relative to benchmark/tasks/, then as direct path
        task_dir = args.benchmark / "tasks" / args.tasks
        if not task_dir.exists():
            task_dir = Path(args.tasks)
        if not task_dir.exists():
            logger.error(f"Task not found: {task_dir}")
            sys.exit(1)
        tasks = [load_task(task_dir)]
        logger.info(f"Loaded task: {tasks[0].name}")

    num_workers = args.parallel or config.workers.evolve
    scheduler = Scheduler(max_workers=num_workers)

    def evolve_single(task) -> EvolutionMetrics:
        verifier = SurrogateVerifier(client=verifier_client)
        oracle = Oracle()

        def skill_loader(skill_name: str) -> str | None:
            local_path = skill_dir / skill_name / "SKILL.md"
            if local_path.exists():
                return local_path.read_text()
            bench_path = args.benchmark / ".agents" / "skills" / skill_name / "SKILL.md"
            if bench_path.exists():
                return bench_path.read_text()
            return None

        _, metrics = run_evolution(
            task=task,
            verifier=verifier,
            oracle=oracle,
            config=config,
            store=store,
            skill_dir=skill_dir,
            client=client,
            meta_skill=meta_skill,
            skill_loader=skill_loader,
        )
        return metrics

    logger.info(f"Running evolution with {num_workers} workers")
    all_metrics = scheduler.map(evolve_single, tasks)

    reporter = Reporter(output_dir)
    report = reporter.report_summary(all_metrics)
    print(report)
    reporter.print_per_task(all_metrics)
    reporter.save_json(all_metrics)
    logger.info(f"Results saved to {output_dir}")


def _load_meta_skill() -> str:
    """Load the Anthropic skill-creator as the meta-skill S_meta."""
    skill_creator_path = Path("skillsbench/.agents/skills/skill-creator/SKILL.md")
    if skill_creator_path.exists():
        return skill_creator_path.read_text()
    return ""


if __name__ == "__main__":
    main()
