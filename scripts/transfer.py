"""Cross-model transfer evaluation (§4.4).

Usage:
    python scripts/transfer.py --skills ./output/skills --models sonnet-4.5,haiku-4.5,qwen3
"""

import argparse
from pathlib import Path

from eval.transfer import evaluate_transfer
from utils.config import Config, load_config
from utils.logger import setup_logger


def main():
    parser = argparse.ArgumentParser(description="Cross-model skill transfer eval")
    parser.add_argument("--config", default="configs/default.yaml", type=Path, help="Config file")
    parser.add_argument("--skills", required=True, type=Path, help="Path to source-evolved skills")
    parser.add_argument("--models", required=True, help="Comma-separated target model IDs")
    parser.add_argument("--output", default="./output/transfer", type=Path, help="Output directory")
    parser.add_argument("--benchmark", default="./skillsbench", type=Path, help="SkillsBench root")
    args = parser.parse_args()

    logger = setup_logger("coevo-transfer")
    logger.info("Cross-model transfer evaluation started")

    _config = load_config(args.config) if Path(args.config).exists() else Config()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    target_models = [m.strip() for m in args.models.split(",")]

    logger.info(f"Target models: {target_models}")

    results = evaluate_transfer(
        skills_dir=args.skills,
        target_models=target_models,
        tasks_dir=args.benchmark,
    )

    print("\nCross-Model Transfer Results:")
    print(f"{'Model':<25} {'With Skills':>12} {'No Skill':>12} {'Delta':>12}")
    print("-" * 61)
    for model, (ws, ns, delta) in results.items():
        print(f"{model:<25} {ws:>11.1f}% {ns:>11.1f}% {delta:>+11.1f}pp")


if __name__ == "__main__":
    main()
