"""Structural integrity tests: frontmatter, path references, doc consistency.

These encode the CONTRIBUTING.md ground rules so drift fails CI instead of
silently breaking auto-triggering or the install story.
"""

from __future__ import annotations

import re
import unittest

from tests.util import REFERENCES_DIR, REPO_ROOT, SCRIPTS_DIR, SKILL_MD, TEMPLATES_DIR, parse_frontmatter

# Fields the two supported runtimes (Claude Code, Codex) are documented to read,
# plus the optional fields the agent-skills format allows.
ALLOWED_TOP_LEVEL_FIELDS = {"name", "description", "metadata", "license", "allowed-tools"}


class FrontmatterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text(encoding="utf-8")
        cls.frontmatter = parse_frontmatter(cls.text)

    def test_name_is_valid_skill_identifier(self):
        name = self.frontmatter.get("name", "")
        self.assertTrue(name, "frontmatter must declare a name")
        self.assertLessEqual(len(name), 64, "skill name must be at most 64 characters")
        self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$", "name must be lowercase letters/digits/hyphens")

    def test_description_present_and_bounded(self):
        description = self.frontmatter.get("description", "")
        self.assertTrue(description, "frontmatter must declare a description (drives auto-triggering)")
        self.assertLessEqual(len(description), 1024, "description must be at most 1024 characters")
        # The description is the trigger surface: it must name the domain and key packages.
        for needle in ("Django", "django-tenants", "multi-tenant"):
            self.assertIn(needle, description)

    def test_no_unknown_top_level_fields(self):
        unknown = set(self.frontmatter) - ALLOWED_TOP_LEVEL_FIELDS
        self.assertFalse(
            unknown,
            f"unknown top-level frontmatter fields {sorted(unknown)}; put extras under metadata: "
            "(unrecognized fields are silently dropped by the runtimes)",
        )

    def test_metadata_version_matches_changelog(self):
        version = self.frontmatter.get("metadata", {}).get("version")
        self.assertTrue(version, "metadata.version must be set")
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, flags=re.M)
        self.assertIsNotNone(match, "CHANGELOG.md must have at least one '## [x.y.z]' entry")
        self.assertEqual(version, match.group(1), "SKILL.md metadata.version must match the latest CHANGELOG entry")


class PathIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_text = SKILL_MD.read_text(encoding="utf-8")

    def test_every_path_referenced_in_skill_md_exists(self):
        referenced = set(re.findall(r"\b(?:references|templates|scripts|hooks)/[A-Za-z0-9_\-./]+", self.skill_text))
        self.assertTrue(referenced, "SKILL.md should reference its supporting files")
        missing = sorted(p for p in referenced if not (REPO_ROOT / p).exists())
        self.assertFalse(missing, f"SKILL.md references missing files: {missing}")

    def test_every_bundled_file_is_referenced_in_skill_md(self):
        bundled = []
        for directory in (REFERENCES_DIR, TEMPLATES_DIR, SCRIPTS_DIR):
            for path in sorted(directory.iterdir()):
                if path.is_file() and not path.name.startswith("."):
                    bundled.append(f"{directory.name}/{path.name}")
        unreferenced = sorted(p for p in bundled if p not in self.skill_text)
        self.assertFalse(
            unreferenced,
            f"bundled files never mentioned in SKILL.md (dead weight or missing docs): {unreferenced}",
        )


class DocConsistencyTests(unittest.TestCase):
    """CONTRIBUTING.md: versions/dates must move together across the docs."""

    @classmethod
    def setUpClass(cls):
        cls.readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        cls.baseline = (REFERENCES_DIR / "99-sources-and-current-baseline.md").read_text(encoding="utf-8")

    def test_baseline_date_is_consistent(self):
        match = re.search(r"prepared on (\d{4}-\d{2}-\d{2})", self.baseline)
        self.assertIsNotNone(match, "99-sources must state its preparation date")
        self.assertIn(match.group(1), self.readme, "README baseline date must match 99-sources")

    def test_package_pins_are_consistent(self):
        for package in ("django-tenants", "django-tenant-users", "django-multitenant"):
            match = re.search(rf"{package}: ([\d][\w.]*)", self.baseline)
            self.assertIsNotNone(match, f"99-sources must pin {package}")
            self.assertIn(
                match.group(1),
                self.readme,
                f"README compatibility table must carry the same {package} version as 99-sources",
            )
