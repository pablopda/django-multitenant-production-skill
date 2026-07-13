"""Shared helpers for the skill's test suite. Standard library only."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
TEMPLATES_DIR = REPO_ROOT / "templates"
REFERENCES_DIR = REPO_ROOT / "references"
SKILL_MD = REPO_ROOT / "SKILL.md"


def load_script(name: str):
    """Import a script from scripts/ by module name without needing a package."""
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses (among others) resolve cls.__module__
    # through sys.modules while the module body runs.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_fixture(root: Path, rel: str, content: str) -> Path:
    """Write a dedented fixture file under root, creating parents."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content), encoding="utf-8")
    return path


def parse_frontmatter(text: str) -> dict:
    """Minimal parser for the simple YAML frontmatter SKILL.md uses.

    Supports top-level `key: value` pairs and one nesting level (e.g. metadata:).
    Not a general YAML parser on purpose: the skill must not require pyyaml.
    """
    match = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.S)
    if not match:
        raise ValueError("no frontmatter block found")
    data: dict = {}
    current_key: str | None = None
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                data[key] = value
                current_key = None
            else:
                data[key] = {}
                current_key = key
        else:
            if current_key is None:
                raise ValueError(f"unexpected indented line: {line!r}")
            key, _, value = line.strip().partition(":")
            data[current_key][key.strip()] = value.strip()
    return data
