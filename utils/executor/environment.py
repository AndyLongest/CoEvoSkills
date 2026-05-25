from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from utils.executor.sandbox import Sandbox


@dataclass
class Environment:
    """A task execution environment.

    Loaded from a SkillsBench task directory, this captures:
      - Input data files (from environment/data/, environment/ root, environment/doc/)
      - Reference documents
      - Pre-installed skills (from environment/skills/)
      - Dockerfile for building the container
    """

    name: str
    root: Path
    instruction: str = ""
    data_files: dict[str, str] = field(default_factory=dict)
    doc_files: dict[str, str] = field(default_factory=dict)
    pre_installed_skills: dict[str, str] = field(default_factory=dict)
    root_files: dict[str, str] = field(default_factory=dict)
    dockerfile: str = ""

    def prepare_sandbox(self, sandbox: Sandbox) -> None:
        """Populate a sandbox with the task environment files.

        NOTE: sandbox.setup() must be called BEFORE calling this method.
        This method does NOT call setup() to avoid overwriting the workspace
        and losing previously installed dependencies.
        """

        for rel_path, content in self.data_files.items():
            sandbox.write_file(f"/app/environment/{rel_path}", content)

        for rel_path, content in self.doc_files.items():
            sandbox.write_file(f"/app/environment/doc/{rel_path}", content)

        for rel_path, content in self.pre_installed_skills.items():
            sandbox.write_file(f"/app/environment/skills/{rel_path}", content)

        for filename, content in self.root_files.items():
            sandbox.write_file(f"/root/{filename}", content)

    def install_skill(self, sandbox: Sandbox, skill_name: str, skill_bundle) -> None:
        """Install an evolved skill into the sandbox environment.

        Writes the skill's SKILL.md and scripts/ into
        /app/environment/skills/{skill_name}/.
        """
        base = f"/app/environment/skills/{skill_name}"
        sandbox.write_file(f"{base}/SKILL.md", skill_bundle.skillell)
        for script_name, content in skill_bundle.scripts.items():
            sandbox.write_file(f"{base}/scripts/{script_name}", content)


def rollout(skill, env: Environment, sandbox: Sandbox, agent_loop, skill_loader=None) -> dict[str, str]:
    """Execute skill S in environment E and collect output artifacts."""
    sandbox.setup(install_deps=_extract_deps(env.dockerfile))
    env.prepare_sandbox(sandbox)
    env.install_skill(sandbox, skill.name, skill)

    if skill_loader:
        agent_loop.set_skill_loader(skill_loader)

    agent_loop.run(env.instruction, skill.name)

    outputs: dict[str, str] = {}
    result = sandbox.run("find /root -type f 2>/dev/null | head -50", timeout=10)
    if result[0] == 0 and result[1]:
        for line in result[1].strip().split("\n"):
            path = line.strip()
            if path:
                content = sandbox.read_file(path)
                outputs[path] = content

    return outputs


def _extract_deps(dockerfile: str) -> list[str]:
    """Extract Python package dependencies from a Dockerfile.

    Looks for RUN pip install lines, handles multi-line (backslash) continuations.
    Strips pip flags (--flag, --flag=val, -x) before extracting package names.
    """
    import re

    # Join lines that end with backslash
    lines = dockerfile.replace("\\\n", " ").split("\n")
    deps: list[str] = []
    for line in lines:
        if "pip" not in line or "install" not in line:
            continue
        # Extract everything after "pip install" (or "pip3 install")
        match = re.search(r"pip3?\s+install\s+(.+)", line)
        if not match:
            continue
        pkgs_str = match.group(1).strip()
        # Remove pip flags before extracting package names
        pkgs_str = re.sub(r'(?:--\S+?=\S+|--\S+|-\w)\s*', '', pkgs_str).strip()
        for token in re.findall(r'(["\']?)([a-zA-Z_][\w\-\.]*)\1', pkgs_str):
            deps.append(token[1])
    return deps
