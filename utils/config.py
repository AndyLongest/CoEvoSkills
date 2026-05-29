from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class EvolutionConfig:
    n: int = 5  # max oracle interventions (N)
    m: int = 15  # max surrogate retries (M)
    beta: float = 0.7  # context usage cap (β)


@dataclass
class TimeoutConfig:
    evolution_multiplier: float = 5.0  # 5× effective 3000s/task
    evaluation: int = 7200  # 7200s/task


@dataclass
class WorkerConfig:
    evolve: int = 4
    eval: int = 10


@dataclass
class OracleConfig:
    partial_credit: bool = False
    converge_threshold: float = 1.0


@dataclass
class SandboxConfig:
    backend: str = "local"  # "docker" | "local" (proot) | "bare"
    image: str = "python:3.12-slim"


@dataclass
class OpenCodeConfig:
    model: str = "deepseek/deepseek-v4-pro"  # opencode provider/model format


@dataclass
class Config:
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    oracle: OracleConfig = field(default_factory=OracleConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    opencode: OpenCodeConfig = field(default_factory=OpenCodeConfig)
    agent_harness: str = "opencode"  # "opencode" | "agentloop"
    llm_model: str = "deepseek-v4-pro"
    verifier_model: str | None = None  # defaults to same as llm_model
    skillsbench_path: str = "./skillsbench"
    output_dir: str = "./output"


def load_config(path: str | Path) -> Config:
    """Load configuration from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    evolution = EvolutionConfig(**data.get("evolution", {}))
    timeout = TimeoutConfig(**data.get("timeout", {}))
    workers = WorkerConfig(**data.get("workers", {}))
    oracle = OracleConfig(**data.get("oracle", {}))
    sandbox = SandboxConfig(**data.get("sandbox", {}))
    opencode = OpenCodeConfig(**data.get("opencode", {}))

    return Config(
        evolution=evolution,
        timeout=timeout,
        workers=workers,
        oracle=oracle,
        sandbox=sandbox,
        opencode=opencode,
        agent_harness=data.get("agent_harness", "opencode"),
        llm_model=data.get("llm_model", "deepseek-v4-pro"),
        verifier_model=data.get("verifier_model"),
        skillsbench_path=data.get("skillsbench_path", "./skillsbench"),
        output_dir=data.get("output_dir", "./output"),
    )


def default_config() -> Config:
    return Config()
