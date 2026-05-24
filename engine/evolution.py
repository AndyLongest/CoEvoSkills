from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from layers.oracle.oracle import Oracle
from layers.skill_generator.generator import SkillGenerator
from layers.surrogate_verifier.verifier import SurrogateVerifier
from repository.skill import SkillBundle, write_skill
from repository.store import ArtifactStore
from repository.task import Task
from utils.config import Config
from utils.executor.executor import Executor
from utils.executor.sandbox import Sandbox
from utils.llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class EvolutionMetrics:
    task_name: str
    rounds: int = 0
    surrogate_retries: int = 0
    oracle_calls: int = 0
    final_reward: float = 0.0
    best_reward: float = 0.0
    converged: bool = False
    history: list[dict] = field(default_factory=list)
    error: str | None = None


def run_evolution(
    task: Task,
    verifier: SurrogateVerifier,
    oracle: Oracle,
    config: Config,
    store: ArtifactStore,
    skill_dir: Path,
    client: LLMClient,
    meta_skill: str = "",
    skill_loader=None,
) -> tuple[SkillBundle | None, EvolutionMetrics]:
    """Algorithm 1: CoEvoSkills co-evolutionary loop.

    Paper structure:
      C ← (I, S_meta)
      S(0) ∼ πθ(·|C)                    Generator generates initial skill
      while n < N and r < M:
        x(i) ← Φ(S(i), E)               Executor runs skill in sandbox
        R̃(i,j) ← evaluate(x(i), V(j))   Surrogate verifier
        if R̃ < 1:
          C ← C ⊕ F(i,j)
          S(i+1) ∼ πθ(·|C)              Generator refines with feedback
          r++; continue
        x̂(i) ← Φ(S(i), E')              Fresh execution for oracle
        R(i) ← oracle(x̂(i))              Ground-truth oracle
        if R == 1: return S*
        V(j+1) ← escalate(V)            Verifier escalates tests
        n++
    """
    metrics = EvolutionMetrics(task_name=task.name)
    n = 0
    r = 0
    R_best = 0.0
    S_best: SkillBundle | None = None
    V: list[str] = []

    store.write_log(task.name, f"Starting evolution: N={config.evolution.n}, M={config.evolution.m}, β={config.evolution.beta}")
    print(f"\n{'='*60}")
    print(f"EVOLVE: {task.name}  |  N={config.evolution.n}, M={config.evolution.m}")
    print(f"{'='*60}")

    sandbox = Sandbox()
    sandbox.setup(install_deps=_extract_deps_from_task(task))

    generator = SkillGenerator(client=client, meta_skill=meta_skill)
    executor = Executor(client=client, max_turns=10, beta=config.evolution.beta)

    try:
        task.environment.prepare_sandbox(sandbox)

        # Build environment context for the Generator
        env_context = _build_environment_context(task)
        if env_context:
            generator.init_context(task.instruction, env_context=env_context)
            store.write_log(task.name, "Environment context injected into generator")

        # === 1. Generate initial skill S(0) ∼ πθ(·|C) ===
        print("  GENERATOR | Generating initial skill...")
        S = generator.generate(task.instruction)
        if S is None:
            S = SkillBundle(name=f"evo-{task.name}", skillell="# Initial skill\n")
        S_best = S
        store.write_log(task.name, f"Initial skill: {S.name}")
        write_skill(S, skill_dir)
        print(f"  GENERATOR | Skill '{S.name}' generated")

        while n < config.evolution.n and r < config.evolution.m:
            metrics.rounds += 1
            round_record: dict = {"round": metrics.rounds, "n": n, "r": r}
            store.write_log(task.name, f"Round {metrics.rounds}: n={n}, r={r}")
            print(f"\n─── ROUND {metrics.rounds} ───  n={n}/{config.evolution.n} oracle  r={r}/{config.evolution.m} surrogate")

            # === 2. Execute skill in sandbox: x(i) ← Φ(S(i), E) ===
            store.write_log(task.name, "Phase: executor")
            print("  EXECUTOR  | Running skill...")
            outputs = executor.execute(S, sandbox, task.instruction, skill_loader=skill_loader)
            round_record["output_count"] = len(outputs)
            store.write_log(task.name,
                f"Executor complete: {len(outputs)} files: {list(outputs.keys())[:5]}")
            print(f"  EXECUTOR  | {len(outputs)} files produced")

            # === 3. Surrogate Verifier: R̃(i,j) ← evaluate(x(i), V(j)) ===
            store.write_log(task.name, "Phase: verifier")
            print(f"  VERIFIER  | Evaluating {len(outputs)} files with {len(V)} tests...")
            r_tilde, feedback, V = verifier.evaluate(task.instruction, outputs, V)
            round_record["r_tilde"] = r_tilde
            store.write_log(task.name,
                f"Surrogate R̃ = {r_tilde:.2f}, tests={len(V)}, outputs={len(outputs)}")
            print(f"  VERIFIER  | R̃ = {r_tilde:.2f}")

            # === 4. If R̃ < 1: refine skill and retry ===
            if r_tilde < 1.0:
                if feedback:
                    generator.append_feedback(feedback.to_context_str())
                    store.write_log(task.name,
                        f"Verifier feedback: {feedback.root_cause_analysis[:100]}...")
                    print("  GENERATOR | Refining skill with feedback...")
                    S = generator.generate(task.instruction, feedback=feedback.to_context_str())
                    if S is None:
                        S = SkillBundle(name=f"evo-{task.name}", skillell="# Fallback skill\n")
                    S_best = S
                    write_skill(S, skill_dir)

                round_record["exit"] = "verifier_fail"
                metrics.history.append(round_record)
                r += 1
                metrics.surrogate_retries += 1
                continue

            # === 5. Ground-Truth Oracle: R(i) ← oracle(x̂(i)) ===
            store.write_log(task.name, "Phase: oracle")
            print("  ORACLE    | Running skill in fresh sandbox...")
            oracle_r, oracle_score = oracle.evaluate(S, task, client, deps=_extract_deps_from_task(task))
            n += 1
            metrics.oracle_calls += 1
            round_record["oracle_reward"] = oracle_r
            store.write_log(task.name, f"Oracle R = {oracle_r}")
            print(f"  ORACLE    | R = {oracle_r}")

            if oracle_r == 1:
                S_best = S
                metrics.final_reward = 1.0
                metrics.best_reward = 1.0
                metrics.converged = True
                round_record["exit"] = "success"
                metrics.history.append(round_record)
                store.write_log(task.name, "CONVERGED: R=1")
                print(f"\n{'='*60}")
                print("  ✓ CONVERGED  |  Reward = 1.0")
                print(f"{'='*60}\n")
                break
            elif oracle_score > R_best:
                R_best = oracle_score
                S_best = S

            metrics.best_reward = R_best

            # === 6. Co-evolution: escalate verifier tests V(j+1) ===
            generator.append_oracle_signal(False)
            V = verifier.escalate(task.instruction, outputs, V)
            round_record["exit"] = "oracle_fail_escalate"
            round_record["V_size"] = len(V)
            metrics.history.append(round_record)
            r += 1

    except Exception as e:
        metrics.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        store.write_log(task.name, f"Error: {metrics.error}")
        print(f"  ERROR: {metrics.error[:200]}")
    finally:
        sandbox.cleanup()

    metrics.final_reward = R_best
    if S_best:
        store.save_skill(S_best, task.name)
        write_skill(S_best, skill_dir)

    return S_best, metrics


def _collect_outputs(sandbox: Sandbox) -> dict[str, str]:
    """Collect output files produced by the agent in /root/ and /app/.

    Returns paths relative to workspace root (no leading /) so the verifier's
    test runner can materialize them inside its temp dir and run assertions
    with os.chdir().
    """
    outputs: dict[str, str] = {}
    for search_dir in ["/root", "/app"]:
        exit_code, stdout, _ = sandbox.run(
            f"find {search_dir} -maxdepth 1 -type f 2>/dev/null", timeout=10
        )
        if exit_code == 0 and stdout:
            for line in stdout.strip().split("\n"):
                abspath = line.strip()
                if abspath and "progress.md" not in abspath:
                    content = sandbox.read_file(abspath)
                    if content:
                        relpath = abspath.lstrip("/")
                        outputs[relpath] = content
    if not outputs:
        # Fallback: search workspace root
        ec, out, _ = sandbox.run("find . -maxdepth 1 -type f 2>/dev/null", timeout=5)
        if ec == 0 and out:
            for line in out.strip().split("\n"):
                path = line.strip()
                if path and "progress.md" not in path:
                    content = sandbox.read_file(path)
                    if content:
                        outputs[path.replace("./", "")] = content
    return outputs


def _read_skill_from_sandbox(sandbox: Sandbox, task_name: str) -> SkillBundle | None:
    """Read the agent-created evo-* skill from the sandbox filesystem."""
    exit_code, stdout, _ = sandbox.run(
        "find /app/environment/skills -name 'SKILL.md' -path '*/evo-*' 2>/dev/null", timeout=5
    )
    if exit_code != 0 or not stdout:
        return None

    skillell_path = stdout.strip().split("\n")[0]
    if not skillell_path:
        return None

    skillell = sandbox.read_file(skillell_path)
    if not skillell:
        return None

    # Extract skill name from path: /app/environment/skills/evo-xxx/SKILL.md → evo-xxx
    parts = Path(skillell_path).parts
    skill_name = "evo-task"
    for i, p in enumerate(parts):
        if p == "skills" and i + 1 < len(parts):
            skill_name = parts[i + 1]
            break

    scripts: dict[str, str] = {}
    scripts_dir = str(Path(skillell_path).parent / "scripts")
    ec2, out2, _ = sandbox.run(f"find {scripts_dir} -type f -not -name '*.pyc' 2>/dev/null", timeout=5)
    if ec2 == 0 and out2:
        for script_path in out2.strip().split("\n"):
            if script_path.strip():
                try:
                    content = sandbox.read_file(script_path.strip())
                except UnicodeDecodeError:
                    continue
                if content:
                    # Store relative to scripts dir
                    rel = str(Path(script_path.strip()).relative_to(scripts_dir))
                    scripts[rel] = content

    return SkillBundle(name=skill_name, skillell=skillell, scripts=scripts)


def _build_environment_context(task: Task) -> str:
    """Build a dense summary of the task's environment files and context.

    This is injected into the Skill Generator's context C so it can
    produce skills tailored to the actual input data, available skills,
    and installed dependencies — without needing an interactive agent loop.
    """
    parts: list[str] = []

    env_dir = task.environment.root / "environment"
    if env_dir.exists():
        root_files = sorted(
            f for f in env_dir.iterdir()
            if f.is_file() and f.name != "Dockerfile"
        )
        for f in root_files:
            try:
                content = f.read_text()
                parts.append(f"### Input file: {f.name}\n```\n{content[:5000]}\n```")
            except UnicodeDecodeError:
                parts.append(f"### Input file: {f.name}  [binary, skipped]")

    if task.environment.data_files:
        parts.append("### Data files in data/:")
        for path, content in task.environment.data_files.items():
            parts.append(f"**{path}**\n```\n{content[:3000]}\n```")

    if task.environment.doc_files:
        parts.append("### Reference documents:")
        for path, content in task.environment.doc_files.items():
            parts.append(f"**{path}**\n```\n{content[:3000]}\n```")

    skill_mds = {
        k: v for k, v in task.environment.pre_installed_skills.items()
        if k.endswith("SKILL.md")
    }
    if skill_mds:
        parts.append("### Pre-installed skills available:")
        for path, content in skill_mds.items():
            parts.append(f"**{path}**\n```\n{content[:2000]}\n```")

    deps = _extract_deps_from_task(task)
    if deps:
        parts.append(f"### Installed Python packages: {', '.join(deps)}")

    return "\n\n".join(parts)


def _extract_deps_from_task(task: Task) -> list[str]:
    """Extract pip dependencies from the task's Dockerfile."""
    import re

    dockerfile = task.environment.dockerfile
    if not dockerfile:
        return []

    lines = dockerfile.replace("\\\n", " ").split("\n")
    deps: list[str] = []

    for line in lines:
        if "pip" not in line or "install" not in line:
            continue
        match = re.search(r"pip3?\s+install\s+(.+)", line)
        if not match:
            continue
        pkgs_str = match.group(1)
        # Remove pip flags (--flag, --flag=val, -x) before extracting package names
        pkgs_str = re.sub(r'(?:--\S+?=\S+|--\S+|-\w)\s*', '', pkgs_str).strip()
        for token in re.findall(r'(["\']?)([a-zA-Z_][\w\-\.]*)\1', pkgs_str):
            deps.append(token[1])

    return deps


def _get_env_files_info(sandbox: Sandbox) -> str:
    """Collect environment file tree for agent context injection.

    Equivalent to running: ls -la /app/environment/ && find /app/environment/ -type f
    """
    lines: list[str] = []
    ec, out, _ = sandbox.run("ls -la /app/environment/ 2>/dev/null", timeout=5)
    if ec == 0 and out:
        lines.append(out.strip())

    ec, out, _ = sandbox.run("find /app/environment/ -type f 2>/dev/null | head -50", timeout=5)
    if ec == 0 and out:
        lines.append("File tree:")
        lines.append(out.strip())

    ec, out, _ = sandbox.run("ls -la /root/ 2>/dev/null", timeout=5)
    if ec == 0 and out:
        lines.append("Root directory:")
        lines.append(out.strip())

    return "\n".join(lines)


def _get_installed_tools(sandbox: Sandbox) -> str:
    """Collect installed Python packages for agent context injection.

    Equivalent to running: pip list
    """
    lines: list[str] = []
    ec, out, _ = sandbox.run("pip list 2>/dev/null | head -60", timeout=10)
    if ec == 0 and out:
        lines.append("Python packages (pip list):")
        lines.append(out.strip())

    ec, out, _ = sandbox.run("python3 --version 2>&1", timeout=5)
    if ec == 0 and out:
        lines.append(f"Python: {out.strip()}")

    return "\n".join(lines)
