#!/usr/bin/env python3
"""Generate starter tenant-isolation test templates.

The templates live in ../templates so there is a single source of truth. This
script copies the appropriate one into the target project; it does not embed its
own copy (that duplication previously drifted out of sync with templates/).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_FILES = {
    "schema": "schema_tenant_isolation_test_template.py",
    "shared": "shared_schema_isolation_test_template.py",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate starter tenant-isolation test template.")
    parser.add_argument("--root", default=".", help="Project root. Default: current directory.")
    parser.add_argument("--mode", choices=("schema", "shared"), required=True, help="Tenancy model test template.")
    parser.add_argument("--output", default="tests/test_tenant_isolation.py", help="Output file path relative to root.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing file.")
    args = parser.parse_args(argv)

    template_path = TEMPLATES_DIR / TEMPLATE_FILES[args.mode]
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read template {template_path}: {exc}", file=sys.stderr)
        return 2

    root = Path(args.root).resolve()
    output = (root / args.output).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        # The documented contract is "relative to root"; an absolute --output or a
        # ../-traversal silently escaping the project is never what the user meant.
        print(f"error: --output must stay inside --root: {output}", file=sys.stderr)
        return 2
    if output == root or output.is_dir():
        print(f"error: --output must be a file path, not a directory: {output}", file=sys.stderr)
        return 2
    if output.exists() and not args.force:
        print(f"error: output exists; use --force to overwrite: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template, encoding="utf-8")

    if args.mode == "schema":
        # The schema template is unittest-style and normally run via `manage.py test`.
        # Since Python 3.11 unittest discovery skips directories that are not importable
        # packages, so a tests/ dir without __init__.py silently never runs — the exact
        # vacuous-green outcome the fail-loudly guards exist to prevent.
        # output was validated to resolve inside root, so walking parents terminates.
        package_dir = output.parent
        while package_dir != root:
            init_file = package_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")
                print(f"wrote: {init_file} (unittest discovery requires a package)")
            package_dir = package_dir.parent
    else:
        print("Note: pytest collects this file without __init__.py; if you run it via "
              "`manage.py test` instead, make the directory a package.")

    print(f"wrote: {output}")
    print("Every generated test fails until you implement it; replace the fail(...) guards with real assertions.")
    print("Review TODOs, wire real fixtures/URLs/models, then add the test to CI.")
    print("Verify it actually runs and fails once, e.g.: python manage.py test <dotted.path> or pytest <path>.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
