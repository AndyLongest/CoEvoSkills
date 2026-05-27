from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from utils.executor.environment import Environment


@dataclass
class Task:
    """A single SkillsBench task.

    Each task has:
        name — unique identifier (directory name)
        instruction — task description (from instruction.md)
        environment — input files, docs, pre-installed skills
        verifier_path — path to ground-truth verifier script (tests/test.sh)
    """

    name: str
    instruction: str
    environment: Environment
    verifier_path: Path = field(default_factory=Path)
    metadata: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Task({self.name!r})"


def load_task(task_dir: str | Path) -> Task:
    """Load a single task from a SkillsBench task directory.

    Expected layout:
        task_dir/
            instruction.md
            task.toml
            environment/
                Dockerfile
                data/          (optional)
                doc/           (optional)
                skills/        (optional)
            tests/
                test.sh
                test_outputs.py
    """
    task_dir = Path(task_dir)
    name = task_dir.name

    instruction = (task_dir / "instruction.md").read_text().strip()

    env_dir = task_dir / "environment"
    env = Environment(
        name=name,
        root=task_dir,
        instruction=instruction,
        data_files=_collect_files(env_dir / "data") if (env_dir / "data").exists() else {},
        doc_files=_collect_files(env_dir / "doc") if (env_dir / "doc").exists() else {},
        pre_installed_skills=_collect_skills(env_dir / "skills") if (env_dir / "skills").exists() else {},
        root_files=_collect_root_files(env_dir),
        dockerfile=(env_dir / "Dockerfile").read_text() if (env_dir / "Dockerfile").exists() else "",
    )

    metadata = {}
    task_toml_path = task_dir / "task.toml"
    if task_toml_path.exists():
        with open(task_toml_path, "rb") as f:
            metadata = tomllib.load(f)

    verifier_path = task_dir / "tests" / "test.sh"

    return Task(
        name=name,
        instruction=instruction,
        environment=env,
        verifier_path=verifier_path,
        metadata=metadata,
    )


def load_all_tasks(benchmark_dir: str | Path) -> list[Task]:
    """Load all tasks from a SkillsBench benchmark directory.

    Scans benchmark_dir/tasks/ for subdirectories containing instruction.md.
    """
    benchmark_dir = Path(benchmark_dir)
    tasks_dir = benchmark_dir / "tasks"
    if not tasks_dir.exists():
        raise FileNotFoundError(f"Tasks directory not found: {tasks_dir}")

    tasks: list[Task] = []
    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        instruction_path = task_dir / "instruction.md"
        if instruction_path.exists():
            tasks.append(load_task(task_dir))

    return tasks


def _collect_root_files(env_dir: Path) -> dict[str, str]:
    """Collect individual files from the environment root directory.

    These are input files placed directly in environment/ (e.g., test.bib).
    Excludes Dockerfile, directories, and already-collected subdirectories.
    Binary files are base64-encoded with a __B64__ marker.
    Returns dict of {filename: content}.
    """
    import base64

    result: dict[str, str] = {}
    if not env_dir.exists():
        return result
    for f in sorted(env_dir.iterdir()):
        if f.is_file() and f.name != "Dockerfile":
            try:
                result[f.name] = f.read_text()
            except UnicodeDecodeError:
                result[f.name] = "__B64__" + base64.b64encode(f.read_bytes()).decode()
    return result


def _collect_files(dir_path: Path) -> dict[str, str]:
    """Collect all files recursively from a directory.

    Returns dict of {relative_path: content}. Binary files are base64-encoded.
    """
    import base64

    result: dict[str, str] = {}
    if not dir_path.exists():
        return result
    for f in sorted(dir_path.rglob("*")):
        if f.is_file():
            try:
                content = f.read_text()
                rel_path = str(f.relative_to(dir_path))
                result[rel_path] = content
            except UnicodeDecodeError:
                rel_path = str(f.relative_to(dir_path))
                result[rel_path] = "__B64__" + base64.b64encode(f.read_bytes()).decode()
    return result


def _collect_skills(skills_dir: Path) -> dict[str, str]:
    """Collect all skill files from a skills directory.

    SkillsBench skills are subdirectories containing SKILL.md files.

    Returns dict of {skill_name/SKILL.md: content, ...}.
    """
    result: dict[str, str] = {}
    if not skills_dir.exists():
        return result
    for skill_dir in sorted(skills_dir.iterdir()):
        if skill_dir.is_dir():
            for f in sorted(skill_dir.rglob("*")):
                if f.is_file():
                    rel_path = str(f.relative_to(skills_dir))
                    result[rel_path] = f.read_text()
    return result
