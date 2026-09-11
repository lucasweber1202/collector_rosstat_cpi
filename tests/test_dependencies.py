"""The fleet forbids a set of packages; the declared dependencies must match."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {
    "requests",
    "python-dotenv",
    "alembic",
    "sqlmodel",
    "pydantic",
    "attrs",
    "beautifulsoup4",
}


def _requirement_names(lines: list[str]) -> set[str]:
    names = set()
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        names.add(line.split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip().lower())
    return names


def test_requirements_and_pyproject_declare_the_same_dependencies() -> None:
    requirements = _requirement_names((ROOT / "requirements.txt").read_text().splitlines())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    assert requirements == _requirement_names(project)


def test_no_forbidden_dependency_is_declared() -> None:
    requirements = _requirement_names((ROOT / "requirements.txt").read_text().splitlines())
    assert not requirements & FORBIDDEN


def test_the_schema_name_matches_the_repository_name() -> None:
    from scripts.config import SCHEMA_NAME

    assert SCHEMA_NAME == ROOT.name == "collector_rosstat_cpi"


def test_no_shared_framework_directories_were_introduced() -> None:
    forbidden = {"core", "lib", "utils", "common", "helpers"}
    assert not {path.name for path in (ROOT / "scripts").iterdir() if path.is_dir()} & forbidden
    assert (ROOT / "main.py").exists()
