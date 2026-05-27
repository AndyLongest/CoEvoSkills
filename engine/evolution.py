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
from utils.colors import C
from utils.config import Config
from utils.executor.sandbox import Sandbox
from utils.llm.client import LLMClient

logger = logging.getLogger(__name__)

SKILL_DISCOVERY_HINT = """\
Important: Specialized skills are available. Load relevant skills before starting
to get domain-specific guidance, code utilities, and best practices for this task.
Use the JSON field "load_skill" (e.g., {"load_skill": "skill-name"}).
Background reference documents may be available under /app/environment/doc/.
Read all documents there before starting.
"""


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
    print(f"\n{C.header(f'EVOLVE: {task.name}  |  N={config.evolution.n}, M={config.evolution.m}')}")
    print(f"{C.header('=' * 60)}")

    deps = _extract_deps_from_task(task)

    _install_host_deps(deps)

    sandbox = Sandbox()
    sandbox.setup(install_deps=deps)

    generator = SkillGenerator(client=client, meta_skill=meta_skill)
    if skill_loader:
        generator.set_skill_loader(skill_loader)

    try:
        instruction = task.instruction
        if task.environment.pre_installed_skills:
            instruction = f"{instruction}\n\n{SKILL_DISCOVERY_HINT}"
        task.environment.prepare_sandbox(sandbox)

        # Build environment context for the Generator
        env_context = _build_environment_context(task)
        if env_context:
            store.write_log(task.name, "Environment context injected into generator")

        first_run = True
        pending_feedback: str | None = None

        while n < config.evolution.n and r < config.evolution.m:
            metrics.rounds += 1
            round_record: dict = {"round": metrics.rounds, "n": n, "r": r}
            store.write_log(task.name, f"Round {metrics.rounds}: n={n}, r={r}")
            print(f"\n{C.bold(C.yellow(f'─── ROUND {metrics.rounds} ───  n={n}/{config.evolution.n} oracle  r={r}/{config.evolution.m} surrogate'))}")

            # === 1. Execute skill: x(i) = Φ(S(i), E) (Alg. 1, line 7) ===
            if first_run:
                print(f"  {C.cyan('GENERATOR')} | Generating initial skill and executing...")
                S, outputs = generator.generate_and_execute(
                    instruction, sandbox, env_context=env_context,
                    installed_tools=_get_installed_tools(sandbox),
                )
                first_run = False
            elif pending_feedback:
                print(f"  {C.cyan('GENERATOR')} | Refining skill and re-executing...")
                S, outputs = generator.generate_and_execute(
                    instruction, sandbox,
                    feedback=pending_feedback,
                )
                pending_feedback = None
            else:
                print(f"  {C.cyan('GENERATOR')} | Executing current skill...")
                S, outputs = generator.generate_and_execute(
                    instruction, sandbox,
                )

            if S is None:
                S = SkillBundle(name=f"evo-{task.name}", skillell="# Fallback skill\n")
            S_best = S
            if metrics.rounds == 1:
                store.write_log(task.name, f"Initial skill: {S.name}")
            write_skill(S, skill_dir)
            print(f"  {C.cyan('GENERATOR')} | Skill '{S.name}' generated, {len(outputs)} output files")

            # === 2. Record execution outputs ===
            round_record["output_count"] = len(outputs)
            store.write_log(task.name,
                f"Generator complete: {len(outputs)} files: {list(outputs.keys())[:5]}")
            print(f"  {C.cyan('GENERATOR')} | {len(outputs)} files produced")

            # === 3. Surrogate Verifier: R̃(i,j) ← evaluate(x(i), V(j)) ===
            store.write_log(task.name, "Phase: verifier")

            # Merge input data files (from data/ and environment root) so the
            # Verifier can independently read them and compute expected values
            # for content-level tests, regardless of whether the agent touched them.
            verifier_outputs = dict(outputs)
            for data_path, content in task.environment.data_files.items():
                verifier_outputs[f"root/data/{data_path}"] = content
            for filename, content in task.environment.root_files.items():
                verifier_outputs[f"root/{filename}"] = content

            print(f"  {C.yellow('VERIFIER')}  | Evaluating {len(verifier_outputs)} files ({len(outputs)} agent + {len(task.environment.data_files)} data) with {len(V)} tests...")
            r_tilde, feedback, V = verifier.evaluate(instruction, verifier_outputs, V)
            round_record["r_tilde"] = r_tilde
            store.write_log(task.name,
                f"Surrogate R̃ = {r_tilde:.2f}, tests={len(V)}, outputs={len(outputs)}")
            print(f"  {C.yellow('VERIFIER')}  | R̃ = {r_tilde:.2f}")

            # === 4. If R̃ < 1: refine skill and retry ===
            if r_tilde < 1.0:
                if feedback:
                    store.write_log(task.name,
                        f"Verifier feedback: {feedback.root_cause_analysis[:100]}...")
                    pending_feedback = feedback.to_context_str()

                round_record["exit"] = "verifier_fail"
                metrics.history.append(round_record)
                r += 1
                metrics.surrogate_retries += 1
                continue

            # === 5. Ground-Truth Oracle: R(i) ← oracle(x̂(i)) ===
            store.write_log(task.name, "Phase: oracle")
            print(f"  {C.red('ORACLE')}    | Running skill in fresh sandbox...")
            partial_credit = config.oracle.partial_credit
            converge_threshold = config.oracle.converge_threshold
            oracle_r, oracle_score = oracle.evaluate(
                S, task, client,
                deps=_extract_deps_from_task(task),
                partial_credit=partial_credit,
            )
            n += 1
            metrics.oracle_calls += 1
            round_record["oracle_reward"] = oracle_score
            store.write_log(task.name,
                f"Oracle R={oracle_r} score={oracle_score:.4f}")
            oracle_color = C.green if oracle_score >= converge_threshold else C.red
            print(f"  {oracle_color('ORACLE')}    | R={oracle_r}  score={oracle_color(f'{oracle_score:.4f}')}  (threshold={converge_threshold})")

            if oracle_score >= converge_threshold:
                S_best = S
                R_best = oracle_score
                metrics.final_reward = oracle_score
                metrics.best_reward = oracle_score
                metrics.converged = True
                round_record["exit"] = "success"
                metrics.history.append(round_record)
                store.write_log(task.name, f"CONVERGED: score={oracle_score}")
                print(f"\n{C.success('=' * 60)}")
                print(f"  {C.success(f'✓ CONVERGED  |  Oracle Score = {oracle_score:.4f}')}")
                print(f"{C.success('=' * 60)}\n")
                break
            elif oracle_score > R_best:
                R_best = oracle_score
                S_best = S

            metrics.best_reward = R_best

            # === 6. Co-evolution: escalate verifier tests V(j+1) ===
            generator.append_oracle_signal(oracle_score)
            V = verifier.escalate(instruction, outputs, V)
            round_record["exit"] = "oracle_fail_escalate"
            round_record["V_size"] = len(V)
            metrics.history.append(round_record)
            r += 1

    except Exception as e:
        metrics.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        store.write_log(task.name, f"Error: {metrics.error}")
        print(f"  {C.fail('ERROR')}: {metrics.error[:200]}")
    finally:
        sandbox.cleanup()

    metrics.final_reward = R_best
    if S_best:
        store.save_skill(S_best, task.name)
        write_skill(S_best, skill_dir)

    return S_best, metrics


def _collect_outputs(sandbox: Sandbox) -> dict[str, str]:
    """Collect output files produced by the agent in /root/ and /app/.

    Searches up to depth 3 to catch files the agent extracts into
    subdirectories (e.g., TSV files from zip archives). Excludes
    virtual environments and cache directories.

    Returns paths relative to workspace root (no leading /) so the verifier's
    test runner can materialize them inside its temp dir and run assertions
    with os.chdir().
    """
    outputs: dict[str, str] = {}
    for search_dir in ["/root", "/app"]:
        exit_code, stdout, _ = sandbox.run(
            f"find {search_dir} -maxdepth 3 -type f "
            f"-not -path '*/.venv/*' -not -path '*/__pycache__/*' 2>/dev/null",
            timeout=30,
        )
        if exit_code == 0 and stdout:
            for line in stdout.strip().split("\n"):
                abspath = line.strip()
                if abspath and "progress.md" not in abspath:
                    content = sandbox.read_file(abspath)
                    if content is not None and (content or sandbox.file_exists(abspath)):
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
                    if content is not None and (content or sandbox.file_exists(path)):
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
        # Remove pip flags (--flag=val, --flag, -flag) before extracting package names
        # Split by space and filter out flag tokens to avoid stripping hyphens
        # from package names (e.g., -p in batman-package).
        pkgs_str = ' '.join(
            t for t in pkgs_str.split()
            if not t.startswith('-')
        )
        for token in re.findall(r'(["\']?)([a-zA-Z_][\w\-\.]*)\1', pkgs_str):
            name = token[1]
            # Skip tokens that look like version numbers (pure digits, e.g. "81" from setuptools<81)
            if re.match(r'^\d+(\.\d+)*$', name):
                continue
            deps.append(name)

    return deps


def _install_host_deps(deps: list[str]) -> None:
    """Install pip dependencies on the host for the Verifier's test runner.

    The Verifier's TestRunner runs exec() on the host (not inside the sandbox)
    and needs task-specific Python packages (numpy, lightkurve, etc.) to
    execute content-level test assertions that import them.
    """
    if not deps:
        return
    import subprocess
    import sys

    try:
        logger.info("Installing %d host deps for Verifier: %s", len(deps), ", ".join(deps))
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", *deps],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            logger.warning("Host dep install had issues: %s", result.stderr[:200])
    except subprocess.TimeoutExpired:
        logger.warning("Host dep install timed out after 300s")
    except Exception as e:
        logger.warning("Host dep install failed: %s", e)


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
