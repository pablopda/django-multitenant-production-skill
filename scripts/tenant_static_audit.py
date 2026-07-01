#!/usr/bin/env python3
"""
Static audit helper for Django multi-tenant applications.

This script looks for common tenant-isolation risks in Django codebases.
It is conservative: findings are prompts for human/agent review, not proof of a vulnerability.

No external dependencies required.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

SEVERITY_ORDER = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "Info": 0}

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
    "dist",
    "build",
}

HIGH_RISK_FILE_HINTS = (
    "view",
    "api",
    "serializer",
    "permission",
    "admin",
    "task",
    "job",
    "resolver",
    "schema",
    "mutation",
    "consumer",
    "webhook",
    "export",
    "import",
)

TENANT_WORDS = (
    "tenant",
    "schema",
    "organization",
    "organisation",
    "workspace",
    "account",
    "company",
    "client",
)

TENANT_CONTEXT_WORDS = (
    "request.tenant",
    "tenant_context",
    "schema_context",
    "set_current_tenant",
    "get_current_tenant",
    "connection.schema_name",
    "for_tenant",
    "tenant_id",
    "tenant=",
    "schema_name",
    "BaseTenantCommand",
    "tenant_command",
    "all_tenants_command",
)


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    line: int
    message: str
    evidence: str
    recommendation: str


@dataclass
class ProjectFacts:
    root: str
    packages: dict[str, str]
    detected_stack: list[str]
    settings_files: list[str]
    python_files_scanned: int
    test_files_scanned: int
    tenant_terms_in_tests: bool


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def iter_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix in {".py", ".txt", ".in", ".toml", ".lock", ".cfg", ".ini", ".yml", ".yaml", ".md"}:
                yield path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def line_at(text: str, line: int) -> str:
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return dotted_name(node.value)
    return ""


def contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def context_window(lines: Sequence[str], lineno: int, radius: int = 8) -> str:
    start = max(0, lineno - 1 - radius)
    end = min(len(lines), lineno + radius)
    return "\n".join(lines[start:end])


def is_test_file(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def is_migration_file(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    return "migrations" in parts and path.suffix == ".py" and path.name != "__init__.py"


def is_high_risk_file(path: Path) -> bool:
    if is_test_file(path):
        return False
    joined = "/".join(p.lower() for p in path.parts)
    if "management/commands" in joined:
        return True
    return any(hint in path.name.lower() or f"/{hint}" in joined for hint in HIGH_RISK_FILE_HINTS)


def parse_requirements_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    # Handle package==version, package>=version, package[extra]==version.
    match = re.match(r"([A-Za-z0-9_.\-]+)(?:\[[^\]]+\])?\s*([<>=!~]=?\s*[^;\s]+)?", stripped)
    if not match:
        return None
    name = match.group(1).lower().replace("_", "-")
    spec = (match.group(2) or "").replace(" ", "")
    return name, spec


def collect_package_facts(root: Path) -> dict[str, str]:
    packages: dict[str, str] = {}
    candidate_names = {
        "requirements.txt",
        "requirements.in",
        "requirements-dev.txt",
        "requirements-prod.txt",
        "pyproject.toml",
        "Pipfile",
        "poetry.lock",
        "uv.lock",
        "setup.cfg",
    }
    interesting = {
        "django",
        "djangorestframework",
        "django-tenants",
        "django-tenant-users",
        "django-multitenant",
        "django-tenant-schemas",
        "tenant-schemas-celery",
        "celery",
        "django-redis",
    }
    for path in iter_files(root):
        if path.name not in candidate_names and "requirements" not in path.name.lower():
            continue
        text = read_text(path)
        lower = text.lower()
        for pkg in interesting:
            if pkg in lower:
                packages.setdefault(pkg, "present")
        if path.name.startswith("requirements"):
            for line in text.splitlines():
                parsed = parse_requirements_line(line)
                if parsed and parsed[0] in interesting:
                    packages[parsed[0]] = parsed[1] or "present"
        elif path.name == "pyproject.toml":
            for pkg in interesting:
                m = re.search(rf"[\"']?{re.escape(pkg)}[\"']?\s*[=><~!]+\s*[\"']?([^\"',\n]+)", lower)
                if m:
                    packages[pkg] = m.group(1).strip()
    return packages


def detect_stack(packages: dict[str, str], all_text: str) -> list[str]:
    stack: list[str] = []
    lower = all_text.lower()
    if "django-tenants" in packages or "django_tenants" in lower:
        stack.append("django-tenants / schema-per-tenant")
    if "django-tenant-users" in packages or "tenant_users" in lower or "django_tenant_users" in lower:
        stack.append("django-tenant-users / global users with tenant permissions")
    if "django-multitenant" in packages or "django_multitenant" in lower:
        stack.append("django-multitenant / shared schema tenant_id")
    if "django-tenant-schemas" in packages or "tenant_schemas" in lower:
        stack.append("django-tenant-schemas / legacy schema-per-tenant")
    if not stack and contains_any(lower, TENANT_WORDS):
        stack.append("custom or unknown tenant implementation")
    return stack


def audit_settings(path: Path, root: Path, text: str, findings: list[Finding]) -> None:
    rel = relpath(path, root)
    lower = text.lower()
    is_settings = path.name.startswith("settings") or "settings" in [p.lower() for p in path.parts]
    if not is_settings:
        return

    uses_django_tenants = "django_tenants" in lower or "django-tenants" in lower
    if uses_django_tenants:
        checks = [
            ("django_tenants.postgresql_backend", "DATABASES default ENGINE should use django_tenants.postgresql_backend."),
            ("django_tenants.routers.tenantsyncrouter", "DATABASE_ROUTERS should include django_tenants.routers.TenantSyncRouter."),
            ("tenantmainmiddleware", "TenantMainMiddleware should be first or very near the top of MIDDLEWARE."),
            ("shared_apps", "SHARED_APPS should be declared and reviewed."),
            ("tenant_apps", "TENANT_APPS should be declared and reviewed."),
            ("tenant_model", "TENANT_MODEL should point to the tenant model."),
            ("tenant_domain_model", "TENANT_DOMAIN_MODEL should point to the domain model."),
        ]
        for needle, message in checks:
            if needle not in lower:
                findings.append(Finding(
                    severity="High",
                    rule="DT-SETTINGS-MISSING",
                    path=rel,
                    line=1,
                    message=message,
                    evidence=f"Missing `{needle}` in settings-like file.",
                    recommendation="Review django-tenants settings: database backend, router, middleware, SHARED_APPS, TENANT_APPS, TENANT_MODEL, and TENANT_DOMAIN_MODEL.",
                ))

        mw_match = re.search(r"MIDDLEWARE\s*=\s*[\[(](.*?)[\])]", text, flags=re.S)
        if mw_match and "TenantMainMiddleware" in mw_match.group(1):
            middleware_block = mw_match.group(1)
            non_comment_lines = [ln.strip() for ln in middleware_block.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            tenant_line_index = next((i for i, ln in enumerate(non_comment_lines) if "TenantMainMiddleware" in ln), None)
            if tenant_line_index is not None and tenant_line_index > 1:
                findings.append(Finding(
                    severity="High",
                    rule="DT-MIDDLEWARE-ORDER",
                    path=rel,
                    line=text[:mw_match.start()].count("\n") + 1,
                    message="Tenant middleware is not at the top of MIDDLEWARE.",
                    evidence=non_comment_lines[tenant_line_index],
                    recommendation="Move TenantMainMiddleware before middleware that may touch request, session, auth, URL routing, or database-backed state.",
                ))

        if "caches" in lower and "key_function" not in lower and "django_tenants.cache.make_key" not in lower:
            findings.append(Finding(
                severity="Medium",
                rule="DT-CACHE-KEY-FUNCTION",
                path=rel,
                line=1,
                message="Cache configuration appears present but no tenant-aware KEY_FUNCTION was found.",
                evidence="CACHES found without django_tenants.cache.make_key/KEY_FUNCTION.",
                recommendation="Ensure tenant-specific cache entries include schema/tenant in the key. For django-tenants, consider django_tenants.cache.make_key.",
            ))

        if "tenantcontextfilter" not in lower and "logging" in lower:
            findings.append(Finding(
                severity="Low",
                rule="DT-LOGGING-CONTEXT",
                path=rel,
                line=1,
                message="Logging is configured but tenant context logging was not detected.",
                evidence="LOGGING found without TenantContextFilter.",
                recommendation="Add tenant/schema/domain context to logs for auditability and incident response.",
            ))

    if "show_public_if_no_tenant_found" in lower and "true" in lower:
        findings.append(Finding(
            severity="Medium",
            rule="DT-PUBLIC-FALLBACK",
            path=rel,
            line=1,
            message="SHOW_PUBLIC_IF_NO_TENANT_FOUND appears enabled.",
            evidence="SHOW_PUBLIC_IF_NO_TENANT_FOUND = True",
            recommendation="Confirm this fallback cannot expose tenant-specific routes or confuse tenant resolution. Prefer fail-closed behavior for tenant app routes.",
        ))

    if "x-tenant-id" in lower or "http_x_tenant" in lower:
        findings.append(Finding(
            severity="High",
            rule="TENANT-HEADER",
            path=rel,
            line=1,
            message="Tenant context may be derived from a client-supplied tenant header.",
            evidence="X-Tenant-ID or HTTP_X_TENANT found in settings/middleware-like text.",
            recommendation="Validate any tenant header against authenticated membership; do not trust raw client-supplied tenant identifiers.",
        ))


def audit_python_file(path: Path, root: Path, text: str, findings: list[Finding]) -> None:
    rel = relpath(path, root)
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        findings.append(Finding(
            severity="Info",
            rule="PY-SYNTAX-SKIP",
            path=rel,
            line=exc.lineno or 1,
            message="Could not parse Python file for AST-based checks.",
            evidence=str(exc),
            recommendation="Review manually if this file is relevant to tenant isolation.",
        ))
        return

    lines = text.splitlines()
    high_risk = is_high_risk_file(path)
    migration = is_migration_file(path)
    joined_path = "/".join(p.lower() for p in path.parts)

    class_stack: list[str] = []
    function_stack: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            bases = [dotted_name(base) for base in node.bases]
            if any(base.endswith(("TenantMixin", "DomainMixin", "TenantBase", "TenantModel")) for base in bases):
                findings.append(Finding(
                    severity="Info",
                    rule="TENANT-MODEL-DETECTED",
                    path=rel,
                    line=node.lineno,
                    message=f"Detected tenant-related model `{node.name}`.",
                    evidence=f"class {node.name}({', '.join(bases)})",
                    recommendation="Verify tenant lifecycle, schema naming, domain verification, and deletion policy are documented.",
                ))

            has_model_base = any(base.endswith("Model") or base == "models.Model" for base in bases)
            class_source = ast.get_source_segment(text, node) or ""
            has_tenant_field = re.search(r"\b(tenant|account|organization|workspace|client)\s*=\s*models\.", class_source, re.I)
            if has_model_base and has_tenant_field:
                if "UniqueConstraint" not in class_source and "unique_together" not in class_source:
                    findings.append(Finding(
                        severity="Medium",
                        rule="SHARED-CONSTRAINTS",
                        path=rel,
                        line=node.lineno,
                        message=f"Model `{node.name}` appears tenant-owned but no tenant-scoped uniqueness constraints were detected.",
                        evidence="Tenant-like field found without UniqueConstraint/unique_together in class body.",
                        recommendation="For shared-schema tenant-owned models, add tenant-scoped unique constraints and indexes where relevant.",
                    ))

                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and dotted_name(child.func).startswith("models."):
                        for kw in child.keywords:
                            if kw.arg == "unique" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                findings.append(Finding(
                                    severity="Medium",
                                    rule="SHARED-GLOBAL-UNIQUE",
                                    path=rel,
                                    line=getattr(child, "lineno", node.lineno),
                                    message=f"Model `{node.name}` has `unique=True` on a field and appears tenant-owned.",
                                    evidence=line_at(text, getattr(child, "lineno", node.lineno)),
                                    recommendation="Ensure uniqueness is scoped per tenant unless the field is intentionally globally unique.",
                                ))

            class_stack.append(node.name)
            self.generic_visit(node)
            class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            function_stack.append(node)
            self.generic_visit(node)
            function_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            function_stack.append(node)
            self.generic_visit(node)
            function_stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            name = dotted_name(node.func)
            lineno = getattr(node, "lineno", 1)
            evidence = line_at(text, lineno)
            window = context_window(lines, lineno)
            window_lower = window.lower()
            has_context = contains_any(window, TENANT_CONTEXT_WORDS)

            if high_risk and re.search(r"\.objects\.(all|get|filter|exclude|update|delete|bulk_create|bulk_update)\b", name):
                method = name.split(".objects.")[-1]
                if method in {"all", "get", "update", "delete", "bulk_create", "bulk_update"} and not has_context:
                    sev = "High" if method in {"get", "update", "delete"} else "Medium"
                    findings.append(Finding(
                        severity=sev,
                        rule="ORM-UNSCOPED-HIGH-RISK",
                        path=rel,
                        line=lineno,
                        message=f"Potential unscoped ORM `{method}` call in a tenant-sensitive file.",
                        evidence=evidence,
                        recommendation="Scope by tenant/queryset or ensure schema context is already set. Add a cross-tenant negative test for this path.",
                    ))
                elif method in {"filter", "exclude"} and not contains_any(window, TENANT_WORDS + ("for_tenant",)):
                    findings.append(Finding(
                        severity="Medium",
                        rule="ORM-FILTER-NO-TENANT-HINT",
                        path=rel,
                        line=lineno,
                        message="Potential tenant-owned query filter without tenant hint in nearby code.",
                        evidence=evidence,
                        recommendation="Confirm this model is global or add tenant scoping. If schema-per-tenant, ensure this code cannot run before tenant middleware/context.",
                    ))

            if high_risk and name.endswith("get_object_or_404") and not has_context:
                call_source = ast.get_source_segment(text, node) or evidence
                if not contains_any(call_source, TENANT_WORDS):
                    findings.append(Finding(
                        severity="High",
                        rule="GET-OBJECT-OR-404-UNSCOPED",
                        path=rel,
                        line=lineno,
                        message="`get_object_or_404` call appears unscoped by tenant.",
                        evidence=evidence,
                        recommendation="Use a tenant-scoped queryset, e.g. get_object_or_404(Model.objects.for_tenant(request.tenant), pk=...).",
                    ))

            if high_risk and name.endswith("objects.all") and "queryset" in window_lower and not has_context:
                findings.append(Finding(
                    severity="High",
                    rule="DRF-GLOBAL-QUERYSET",
                    path=rel,
                    line=lineno,
                    message="DRF/admin-like global queryset may expose cross-tenant data.",
                    evidence=evidence,
                    recommendation="Override get_queryset() and derive objects from current tenant or verified schema context.",
                ))

            if name in {"cache.get", "cache.set", "cache.add", "cache.get_or_set", "cache.delete", "cache.incr", "cache.decr"}:
                first_arg = node.args[0] if node.args else None
                literal = first_arg.value if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str) else None
                if literal and not contains_any(literal, TENANT_WORDS + ("schema",)):
                    findings.append(Finding(
                        severity="Medium",
                        rule="CACHE-GLOBAL-KEY",
                        path=rel,
                        line=lineno,
                        message="Cache call uses a static key without tenant/schema hint.",
                        evidence=evidence,
                        recommendation="Include tenant/schema in cache keys for tenant-specific data, or document that this cache entry is global/public.",
                    ))

            if name.startswith("models."):
                for kw in node.keywords:
                    if kw.arg == "upload_to" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        upload_to = kw.value.value
                        if not contains_any(upload_to, TENANT_WORDS + ("schema", "%s", "{}")):
                            findings.append(Finding(
                                severity="Medium",
                                rule="FILE-UPLOAD-GLOBAL-PATH",
                                path=rel,
                                line=lineno,
                                message="FileField/ImageField upload path has no tenant/schema hint.",
                                evidence=evidence,
                                recommendation="Use a tenant-prefixed upload path or tenant-aware storage for tenant-owned files.",
                            ))

            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            lineno = getattr(node, "lineno", 1)
            evidence = line_at(text, lineno)
            target_names = [dotted_name(t) for t in node.targets]
            if high_risk and any(t.endswith("queryset") or t == "queryset" for t in target_names):
                value_name = dotted_name(node.value)
                if value_name.endswith("objects.all") and not contains_any(evidence, TENANT_CONTEXT_WORDS):
                    findings.append(Finding(
                        severity="High",
                        rule="DRF-QUERYSET-ASSIGNMENT",
                        path=rel,
                        line=lineno,
                        message="Class-level `queryset = Model.objects.all()` found in tenant-sensitive file.",
                        evidence=evidence,
                        recommendation="Use get_queryset() and tenant-scoped managers/querysets for tenant-owned models.",
                    ))
            self.generic_visit(node)

    Visitor().visit(tree)

    # File-level checks that need whole-file context.
    lower = text.lower()
    if high_risk and ("@shared_task" in text or "@app.task" in text or "celery" in lower):
        has_orm = ".objects." in text
        has_tenant_context = contains_any(text, TENANT_CONTEXT_WORDS)
        if has_orm and not has_tenant_context:
            findings.append(Finding(
                severity="High",
                rule="ASYNC-NO-TENANT-CONTEXT",
                path=rel,
                line=1,
                message="Celery/task-like file touches ORM but no tenant context helper was detected.",
                evidence="Task/celery marker + `.objects.` found without tenant_context/schema_context/tenant hint.",
                recommendation="Pass tenant ID/schema into tasks and set tenant context before ORM access. Add mismatch tenant/object tests.",
            ))

    if "management/commands" in joined_path and ".objects." in text:
        has_command_context = contains_any(text, ("BaseTenantCommand", "tenant_context", "schema_context", "tenant_command", "all_tenants_command", "--schema", "get_tenant_model"))
        if not has_command_context:
            findings.append(Finding(
                severity="High",
                rule="COMMAND-NO-TENANT-CONTEXT",
                path=rel,
                line=1,
                message="Management command touches ORM without obvious tenant context.",
                evidence="management/commands file + `.objects.` found without tenant-aware command/context hints.",
                recommendation="Use BaseTenantCommand, tenant_command/all_tenants_command, or explicit validated tenant iteration/context.",
            ))

    if migration and "RunPython" in text and not contains_any(text, ("schema_context", "tenant_context", "migrate_schemas", "get_tenant_model", "tenant")):
        findings.append(Finding(
            severity="Medium",
            rule="MIGRATION-RUNPYTHON-NO-TENANT-HINT",
            path=rel,
            line=1,
            message="Data migration uses RunPython without tenant/schema hints.",
            evidence="RunPython found in migration file without tenant/schema context terms.",
            recommendation="Confirm whether this migration runs on public schema, tenant schemas, or both. Test on multiple tenants.",
        ))


def audit_project(root: Path) -> tuple[ProjectFacts, list[Finding]]:
    findings: list[Finding] = []
    packages = collect_package_facts(root)

    all_text_parts: list[str] = []
    settings_files: list[str] = []
    py_count = 0
    test_count = 0
    tenant_terms_in_tests = False

    files = list(iter_files(root))
    for path in files:
        # Keep all text bounded enough for detection; skip huge locks after package collection.
        if path.stat().st_size > 2_000_000:
            continue
        text = read_text(path)
        all_text_parts.append(text[:100_000])
        if path.suffix == ".py":
            py_count += 1
            if is_test_file(path):
                test_count += 1
                if contains_any(text, ("TenantTestCase", "TenantClient", "tenant_a", "tenant_b", "schema_context", "tenant_context", "for_tenant")):
                    tenant_terms_in_tests = True
            if path.name.startswith("settings") or "settings" in [p.lower() for p in path.parts]:
                settings_files.append(relpath(path, root))
            audit_settings(path, root, text, findings)
            audit_python_file(path, root, text, findings)

    all_text = "\n".join(all_text_parts)
    stack = detect_stack(packages, all_text)

    if stack and py_count and test_count == 0:
        findings.append(Finding(
            severity="High",
            rule="TESTS-NOT-DETECTED",
            path=".",
            line=1,
            message="Multi-tenant implementation detected, but no Python test files were found.",
            evidence=", ".join(stack),
            recommendation="Add tenant A/B isolation tests for APIs, admin, tasks, cache, and files.",
        ))
    elif stack and not tenant_terms_in_tests:
        findings.append(Finding(
            severity="High",
            rule="TENANT-TESTS-NOT-DETECTED",
            path=".",
            line=1,
            message="Multi-tenant implementation detected, but tenant-isolation test terms were not found.",
            evidence=f"test_files={test_count}, stack={', '.join(stack)}",
            recommendation="Add negative tests proving tenant A cannot read/mutate/list/export tenant B data.",
        ))

    if "django-tenant-schemas" in packages:
        findings.append(Finding(
            severity="Medium",
            rule="LEGACY-TENANT-SCHEMAS",
            path="requirements/pyproject",
            line=1,
            message="`django-tenant-schemas` detected.",
            evidence=f"django-tenant-schemas {packages.get('django-tenant-schemas')}",
            recommendation="Confirm this legacy dependency is intentionally supported. For new builds, evaluate django-tenants.",
        ))

    facts = ProjectFacts(
        root=str(root),
        packages=packages,
        detected_stack=stack,
        settings_files=settings_files,
        python_files_scanned=py_count,
        test_files_scanned=test_count,
        tenant_terms_in_tests=tenant_terms_in_tests,
    )
    findings.sort(key=lambda f: (-SEVERITY_ORDER.get(f.severity, 0), f.path, f.line, f.rule))
    return facts, findings


def render_markdown(facts: ProjectFacts, findings: list[Finding]) -> str:
    counts = {sev: 0 for sev in ["Critical", "High", "Medium", "Low", "Info"]}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1

    lines: list[str] = []
    lines.append("# Django Multi-Tenant Static Audit")
    lines.append("")
    lines.append(f"Root: `{facts.root}`")
    lines.append(f"Python files scanned: {facts.python_files_scanned}")
    lines.append(f"Test files scanned: {facts.test_files_scanned}")
    lines.append(f"Tenant-isolation test terms detected: {'yes' if facts.tenant_terms_in_tests else 'no'}")
    lines.append("")
    lines.append("## Detected stack")
    if facts.detected_stack:
        for item in facts.detected_stack:
            lines.append(f"- {item}")
    else:
        lines.append("- No obvious Django multi-tenant stack detected. Review manually if this is unexpected.")
    if facts.packages:
        lines.append("")
        lines.append("## Relevant packages")
        for name, spec in sorted(facts.packages.items()):
            lines.append(f"- `{name}`: {spec}")
    lines.append("")
    lines.append("## Finding counts")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    for sev in ["Critical", "High", "Medium", "Low", "Info"]:
        lines.append(f"| {sev} | {counts.get(sev, 0)} |")
    lines.append("")
    if not findings:
        lines.append("No findings. This does not prove tenant isolation; run the full validation checklist and tests.")
        return "\n".join(lines)

    lines.append("## Findings")
    lines.append("")
    lines.append("| Severity | Rule | Location | Message | Recommendation |")
    lines.append("|---|---|---|---|---|")
    for f in findings:
        location = f"`{f.path}:{f.line}`"
        msg = f.message.replace("|", "\\|")
        rec = f.recommendation.replace("|", "\\|")
        lines.append(f"| {f.severity} | `{f.rule}` | {location} | {msg}<br><br>Evidence: `{f.evidence[:240].replace('|', '\\|')}` | {rec} |")

    lines.append("")
    lines.append("## Suggested next steps")
    if counts.get("Critical", 0) or counts.get("High", 0):
        lines.append("1. Treat Critical/High findings as release blockers until reviewed or tested safe.")
        lines.append("2. Add tenant A/B negative tests for each high-risk path.")
        lines.append("3. Review async jobs, admin, cache, files, and migrations manually; static scanning is not enough.")
    else:
        lines.append("1. Manually review Medium findings and confirm tenant isolation tests cover the changed surfaces.")
        lines.append("2. Run the project test suite and migration rehearsal on multiple tenants.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static audit for Django multi-tenant isolation risks.")
    parser.add_argument("--root", default=".", help="Project root to scan. Default: current directory.")
    parser.add_argument("--format", choices={"markdown", "json"}, default="markdown", help="Output format.")
    parser.add_argument("--fail-on", choices=["Critical", "High", "Medium", "Low", "Info"], help="Exit non-zero if any finding at or above this severity exists.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: root does not exist: {root}", file=sys.stderr)
        return 2

    facts, findings = audit_project(root)

    if args.format == "json":
        print(json.dumps({"facts": asdict(facts), "findings": [asdict(f) for f in findings]}, indent=2, sort_keys=True))
    else:
        print(render_markdown(facts, findings))

    if args.fail_on:
        threshold = SEVERITY_ORDER[args.fail_on]
        if any(SEVERITY_ORDER.get(f.severity, 0) >= threshold for f in findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
