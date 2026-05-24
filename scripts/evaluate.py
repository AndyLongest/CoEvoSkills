"""Evaluate with pre-evolved skills on SkillsBench tasks.

Usage:
    python scripts/evaluate.py --skills ./output/skills --model gpt-5.2
"""

import argparse
from pathlib import Path

from eval.reporter import Reporter
from repository.task import load_all_tasks, load_task
from utils.config import Config, load_config
from utils.logger import setup_logger


def main():
    parser = argparse.ArgumentParser(description="CoEvoSkills evaluation")
    parser.add_argument("--config", default="configs/default.yaml", type=Path, help="Config file")
    parser.add_argument("--skills", required=True, type=Path, help="Path to evolved skills directory")
    parser.add_argument("--tasks", default="all", help="Task name or 'all'")
    parser.add_argument("--model", required=True, help="LLM model for evaluation")
    parser.add_argument("--output", default="./output/eval", type=Path, help="Output directory")
    parser.add_argument("--benchmark", default="./skillsbench", type=Path, help="SkillsBench root")
    parser.add_argument("--no-skill-baseline", action="store_true", help="Also run no-skill baseline")
    args = parser.parse_args()

    logger = setup_logger("coevo-eval")
    logger.info("CoEvoSkills evaluation started")

    _config = load_config(args.config) if Path(args.config).exists() else Config()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.tasks == "all":
        tasks = load_all_tasks(args.benchmark)
    else:
        tasks = [load_task(args.benchmark / "tasks" / args.tasks)]

    logger.info(f"Loaded {len(tasks)} tasks for evaluation with model {args.model}")

    # TODO: Run oracle evaluation with pre-evolved skills installed
    # This requires setting up the agent harness for the target model
    logger.info("Evaluation not yet fully implemented — requires agent harness integration")

    _reporter = Reporter(output_dir)
    logger.info(f"Evaluation with model {args.model}: TBD")


if __name__ == "__main__":
    main()
