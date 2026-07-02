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
    parser.add_argument("--mode", choices={"schema", "shared"}, required=True, help="Tenancy model test template.")
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
    output = root / args.output
    if output.exists() and not args.force:
        print(f"error: output exists; use --force to overwrite: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template, encoding="utf-8")
    print(f"wrote: {output}")
    print("Every generated test fails until you implement it; replace the fail(...) guards with real assertions.")
    print("Review TODOs, wire real fixtures/URLs/models, then add the test to CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
