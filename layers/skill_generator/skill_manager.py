from __future__ import annotations

from pathlib import Path

from repository.skill import SkillBundle, parse_skill_dir, write_skill


class SkillManager:
    """Manages the lifecycle of skill files in the filesystem.

    Skills are structured bundles containing:
        SKILL.md          — procedural workflow instructions
        scripts/          — executable utility functions
    """

    def __init__(self, skills_dir: str | Path):
        self.skills_dir = Path(skills_dir)

    def create(self, skill: SkillBundle) -> Path:
        """Write a new skill to disk."""
        return write_skill(skill, self.skills_dir)

    def read(self, name: str) -> SkillBundle | None:
        """Parse an existing skill from disk."""
        skill_dir = self.skills_dir / name
        if not (skill_dir / "SKILL.md").exists():
            return None
        return parse_skill_dir(skill_dir)

    def update(self, skill: SkillBundle) -> Path:
        """Overwrite an existing skill."""
        return write_skill(skill, self.skills_dir)

    def list_skills(self) -> list[str]:
        """Return names of all available skills."""
        names: list[str] = []
        if not self.skills_dir.exists():
            return names
        for d in sorted(self.skills_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                names.append(d.name)
        return names

    def remove(self, name: str) -> None:
        """Remove a skill directory."""
        import shutil

        skill_dir = self.skills_dir / name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
