#!/usr/bin/env python3
"""
Static audit helper for Django multi-tenant applications.

This script looks for common tenant-isolation risks in Django codebases.
It is conservative: findings are prompts for human/agent review, not proof of a vulnerability.

Tenant terminology is configurable. Many SaaS apps do not call their tenant a "tenant" --
they use organization, account, workspace, company, etc. Pass --tenant-term (repeatable)
so the ORM/scoping heuristics recognize the noun your project actually uses. When omitted,
a sensible default set is used and the audit also tries to infer extra terms from settings
(TENANT_MODEL) and tenant model class names.

No external dependencies required. Runs on CPython 3.8+.
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
from typing import Iterator, Sequence

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

# Broad terms used only to guess that *some* tenant concept exists (stack detection).
TENANT_WORDS = (
    "tenant",
    "schema",
    "organization",
    "organisation",
    "workspace",
    "account",
    "company",
    "org",
    "client",
)

# Default tenant "nouns" used to build the scoping/context heuristics. Override with
# --tenant-term for projects that call the tenant something else. "client" is intentionally
# excluded here (too noisy: api_client, self.client, TenantClient); it is added back
# automatically when inferred from a real tenant model named Client.
DEFAULT_TENANT_TERMS = (
    "tenant",
    "organization",
    "organisation",
    "account",
    "workspace",
    "company",
    "org",
)

# Framework API tokens that indicate tenant context regardless of the project's own noun.
FRAMEWORK_CONTEXT_WORDS = (
    "request.tenant",
    "tenant_context",
    "schema_context",
    "set_current_tenant",
    "get_current_tenant",
    "unset_current_tenant",
    "connection.schema_name",
    "schema_name",
    "BaseTenantCommand",
    "tenant_command",
    "all_tenants_command",
)

# Request attributes that carry client-controlled input (never a trustworthy tenant id).
CLIENT_TENANT_SOURCES = (
    "request.get",
    "request.post",
    "request.data",
    "request.query_params",
    "request.headers",
    "request.meta",
    "request.cookies",
    "kwargs",
)

# Assignment markers that identify a Django settings module even without a "settings" path.
SETTINGS_MARKERS = (
    "INSTALLED_APPS",
    "MIDDLEWARE",
    "DATABASES",
    "ROOT_URLCONF",
    "SHARED_APPS",
    "TENANT_APPS",
    "WSGI_APPLICATION",
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
    tenant_terms: list[str]
    python_files_scanned: int
    test_files_scanned: int
    tenant_terms_in_tests: bool


@dataclass
class TenantVocab:
    """Project-specific vocabulary used by the scoping heuristics."""

    terms: tuple[str, ...]
    context_words: tuple[str, ...]
    scoping_hints: tuple[str, ...]
    field_regex: "re.Pattern[str]"


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def rel_parts(path: Path, root: Path) -> list[str]:
    """Path components *relative to the scan root*, lowercased.

    Classifying files by absolute path.parts leaks the checkout location into the results
    (e.g. auditing under /home/ci/tests/proj would mark every file as a test file).
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return [p.lower() for p in rel.parts]


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


def is_test_file(path: Path, root: Path) -> bool:
    parts = set(rel_parts(path, root))
    name = path.name.lower()
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def is_migration_file(path: Path, root: Path) -> bool:
    parts = rel_parts(path, root)
    return "migrations" in parts and path.suffix == ".py" and path.name != "__init__.py"


def is_high_risk_file(path: Path, root: Path) -> bool:
    if is_test_file(path, root):
        return False
    joined = "/".join(rel_parts(path, root))
    if "management/commands" in joined:
        return True
    return any(hint in path.name.lower() or f"/{hint}" in joined for hint in HIGH_RISK_FILE_HINTS)


def looks_like_settings(path: Path, root: Path, text: str) -> bool:
    if path.suffix != ".py":
        return False
    name = path.name.lower()
    parts = rel_parts(path, root)
    if name.startswith("settings") or "settings" in parts:
        return True
    # Layouts like config/base.py or config/production.py: identify by settings markers.
    hits = sum(1 for marker in SETTINGS_MARKERS if re.search(rf"\b{marker}\s*=", text))
    return hits >= 2


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
    # Match the legacy package without tripping on tenant_schemas_celery (the recommended
    # Celery integration for django-tenants). \b already excludes the "_celery" suffix.
    legacy = "django-tenant-schemas" in packages or re.search(r"\btenant_schemas\b", lower) is not None
    if legacy:
        stack.append("django-tenant-schemas / legacy schema-per-tenant")
    if not stack and contains_any(lower, TENANT_WORDS):
        stack.append("custom or unknown tenant implementation")
    return stack


def _split_identifier(name: str) -> set[str]:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    parts = {snake, name.lower()}
    parts.update(p for p in snake.split("_") if len(p) >= 3)
    return parts


def infer_tenant_terms(all_text: str, base_terms: Sequence[str]) -> tuple[str, ...]:
    """Best-effort inference of the project's tenant noun from settings and model names."""
    terms: set[str] = set(base_terms)
    for m in re.finditer(r"TENANT_MODEL\s*=\s*[\"'][\w.]*?\.(\w+)[\"']", all_text):
        terms.update(_split_identifier(m.group(1)))
    for m in re.finditer(r"tenant_id\s*=\s*[\"'](\w+?)(?:_id)?[\"']", all_text):
        terms.update(_split_identifier(m.group(1)))
    for m in re.finditer(r"class\s+(\w+)\s*\([^)]*\b(?:TenantMixin|TenantBase|TenantModel)\b", all_text):
        terms.update(_split_identifier(m.group(1)))
    return tuple(sorted(t for t in terms if len(t) >= 3))


def build_vocab(terms: Sequence[str]) -> TenantVocab:
    ordered = tuple(dict.fromkeys(t.lower() for t in terms if t))
    if not ordered:
        ordered = DEFAULT_TENANT_TERMS
    context = list(FRAMEWORK_CONTEXT_WORDS)
    for t in ordered:
        context += [f"{t}_id", f"{t}=", f"for_{t}", f"request.{t}", f"set_current_{t}", f"get_current_{t}"]
    scoping = tuple(dict.fromkeys(ordered + ("schema", "for_tenant")))
    field_regex = re.compile(r"\b(" + "|".join(re.escape(t) for t in ordered) + r")\s*=\s*models\.", re.I)
    return TenantVocab(
        terms=ordered,
        context_words=tuple(dict.fromkeys(context)),
        scoping_hints=scoping,
        field_regex=field_regex,
    )


def value_is_client_sourced(node: ast.AST) -> bool:
    dotted = dotted_name(node).lower()
    if dotted.startswith("self."):
        dotted = dotted[len("self."):]
    return dotted.startswith(CLIENT_TENANT_SOURCES)


def audit_settings(path: Path, root: Path, text: str, findings: list[Finding]) -> None:
    if not looks_like_settings(path, root, text):
        return
    rel = relpath(path, root)
    lower = text.lower()

    uses_django_tenants = "django_tenants" in lower or "django-tenants" in lower
    if uses_django_tenants:
        checks = [
            ("django_tenants.postgresql_backend", "DATABASES default ENGINE should use django_tenants.postgresql_backend."),
            ("django_tenants.routers.tenantsyncrouter", "DATABASE_ROUTERS should include django_tenants.routers.TenantSyncRouter."),
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

        # Accept either tenant middleware: hostname-based TenantMainMiddleware or the
        # path-based TenantSubfolderMiddleware (used with TENANT_SUBFOLDER_PREFIX).
        uses_subfolder = "tenantsubfoldermiddleware" in lower
        if "tenantmainmiddleware" not in lower and not uses_subfolder:
            findings.append(Finding(
                severity="High",
                rule="DT-SETTINGS-MISSING",
                path=rel,
                line=1,
                message="TenantMainMiddleware (or TenantSubfolderMiddleware) should be first or very near the top of MIDDLEWARE.",
                evidence="No tenant-resolving middleware found in settings-like file.",
                recommendation="Add django_tenants.middleware.main.TenantMainMiddleware (hostname routing) or django_tenants.middleware.TenantSubfolderMiddleware (subfolder routing) near the top of MIDDLEWARE.",
            ))
        if uses_subfolder and "tenant_subfolder_prefix" not in lower:
            findings.append(Finding(
                severity="High",
                rule="DT-SUBFOLDER-PREFIX-MISSING",
                path=rel,
                line=1,
                message="TenantSubfolderMiddleware is used but TENANT_SUBFOLDER_PREFIX was not found.",
                evidence="TenantSubfolderMiddleware without TENANT_SUBFOLDER_PREFIX.",
                recommendation="Set TENANT_SUBFOLDER_PREFIX (e.g. 'clients') so subfolder tenant resolution works.",
            ))

        mw_match = re.search(r"MIDDLEWARE\s*=\s*[\[(](.*?)[\])]", text, flags=re.S)
        tenant_mw_names = ("TenantMainMiddleware", "TenantSubfolderMiddleware")
        if mw_match and any(n in mw_match.group(1) for n in tenant_mw_names):
            middleware_block = mw_match.group(1)
            non_comment_lines = [ln.strip() for ln in middleware_block.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            tenant_line_index = next(
                (i for i, ln in enumerate(non_comment_lines) if any(n in ln for n in tenant_mw_names)),
                None,
            )
            if tenant_line_index is not None and tenant_line_index > 1:
                findings.append(Finding(
                    severity="High",
                    rule="DT-MIDDLEWARE-ORDER",
                    path=rel,
                    line=text[:mw_match.start()].count("\n") + 1,
                    message="Tenant middleware is not at the top of MIDDLEWARE.",
                    evidence=non_comment_lines[tenant_line_index],
                    recommendation="Move the tenant middleware before middleware that may touch request, session, auth, URL routing, or database-backed state.",
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

    # Match the assignment, not the mere presence of the token: SHOW_PUBLIC_IF_NO_TENANT_FOUND
    # = False plus any other `... = True` in the file used to false-positive here.
    if re.search(r"SHOW_PUBLIC_IF_NO_TENANT_FOUND\s*=\s*True\b", text):
        findings.append(Finding(
            severity="Medium",
            rule="DT-PUBLIC-FALLBACK",
            path=rel,
            line=text[:re.search(r"SHOW_PUBLIC_IF_NO_TENANT_FOUND\s*=\s*True\b", text).start()].count("\n") + 1,
            message="SHOW_PUBLIC_IF_NO_TENANT_FOUND is enabled.",
            evidence="SHOW_PUBLIC_IF_NO_TENANT_FOUND = True",
            recommendation="Confirm this fallback cannot expose tenant-specific routes or confuse tenant resolution. Prefer fail-closed behavior for tenant app routes.",
        ))


def audit_python_file(path: Path, root: Path, text: str, findings: list[Finding], vocab: TenantVocab) -> None:
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
    high_risk = is_high_risk_file(path, root)
    migration = is_migration_file(path, root)
    joined_path = "/".join(rel_parts(path, root))

    tenant_arg_names = {"schema", "schema_name"}
    for t in vocab.terms:
        tenant_arg_names.add(t)
        tenant_arg_names.add(f"{t}_id")

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
            has_tenant_field = vocab.field_regex.search(class_source)
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
            has_context = contains_any(window, vocab.context_words)

            # Client-controlled tenant identifier flowing into a query keyword: the exact
            # class TENANT-HEADER warns about, but sourced from GET/POST/data/kwargs.
            for kw in node.keywords:
                if kw.arg and kw.arg.lower() in tenant_arg_names and value_is_client_sourced(kw.value):
                    findings.append(Finding(
                        severity="High",
                        rule="REQUEST-SOURCED-TENANT-ID",
                        path=rel,
                        line=lineno,
                        message="Tenant identifier appears to come from client-controlled request input.",
                        evidence=evidence,
                        recommendation="Never trust a client-supplied tenant id. Resolve the tenant from the authenticated session/membership or validated domain, then scope the query with that value.",
                    ))
                    break

            # Raw SQL bypasses ORM/tenant scoping and search_path assumptions.
            if high_risk:
                raw_kind = None
                if name.endswith(".raw"):
                    raw_kind = "Model.objects.raw()"
                elif name.endswith(".extra"):
                    raw_kind = "QuerySet.extra()"
                elif name.endswith(".cursor") and "connection" in name.lower():
                    raw_kind = "connection.cursor()"
                elif (name.endswith(".execute") or name.endswith(".executemany")) and "cursor" in name.lower():
                    raw_kind = "cursor.execute()"
                if raw_kind:
                    findings.append(Finding(
                        severity="High",
                        rule="RAW-SQL",
                        path=rel,
                        line=lineno,
                        message=f"Raw SQL ({raw_kind}) bypasses ORM/tenant scoping and search_path assumptions.",
                        evidence=evidence,
                        recommendation="Confirm the schema/tenant context is set for this connection and scope the query explicitly. Raw SQL is the #1 shared-schema leak vector; add a cross-tenant negative test.",
                    ))

            if high_risk and re.search(
                r"\.objects\.(all|get|filter|exclude|update|delete|bulk_create|bulk_update|get_or_create|update_or_create|first|last|values|values_list)\b",
                name,
            ):
                method = name.split(".objects.")[-1]
                high_methods = {"get", "update", "delete", "get_or_create", "update_or_create"}
                medium_methods = {"all", "bulk_create", "bulk_update", "first", "last", "values", "values_list"}
                if method in high_methods and not has_context:
                    findings.append(Finding(
                        severity="High",
                        rule="ORM-UNSCOPED-HIGH-RISK",
                        path=rel,
                        line=lineno,
                        message=f"Potential unscoped ORM `{method}` call in a tenant-sensitive file.",
                        evidence=evidence,
                        recommendation="Scope by tenant/queryset or ensure schema context is already set. Add a cross-tenant negative test for this path.",
                    ))
                elif method in medium_methods and not has_context:
                    findings.append(Finding(
                        severity="Medium",
                        rule="ORM-UNSCOPED-HIGH-RISK",
                        path=rel,
                        line=lineno,
                        message=f"Potential unscoped ORM `{method}` call in a tenant-sensitive file.",
                        evidence=evidence,
                        recommendation="Scope by tenant/queryset or ensure schema context is already set. Add a cross-tenant negative test for this path.",
                    ))
                elif method in {"filter", "exclude"} and not contains_any(window, vocab.scoping_hints):
                    findings.append(Finding(
                        severity="Medium",
                        rule="ORM-FILTER-NO-TENANT-HINT",
                        path=rel,
                        line=lineno,
                        message="Potential tenant-owned query filter without tenant hint in nearby code.",
                        evidence=evidence,
                        recommendation="Confirm this model is global or add tenant scoping. If schema-per-tenant, ensure this code cannot run before tenant middleware/context.",
                    ))

            # Chained bulk mutation, e.g. Model.objects.filter(...).delete() / .update().
            # Manager has no .delete()/.update(); real risk is on the queryset receiver.
            if (
                high_risk
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"delete", "update"}
                and ".objects" in dotted_name(node.func.value)
                and not has_context
                and not contains_any(window, vocab.scoping_hints)
            ):
                findings.append(Finding(
                    severity="High",
                    rule="ORM-BULK-MUTATION-UNSCOPED",
                    path=rel,
                    line=lineno,
                    message=f"Chained bulk `{node.func.attr}()` on a manager queryset may run unscoped across tenants.",
                    evidence=evidence,
                    recommendation="Filter by tenant before .update()/.delete(), or ensure schema context is set. Add a cross-tenant negative test.",
                ))

            if high_risk and name.endswith("get_object_or_404") and not has_context:
                call_source = ast.get_source_segment(text, node) or evidence
                if not contains_any(call_source, vocab.scoping_hints):
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
                if literal and not contains_any(literal, vocab.scoping_hints):
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
                        if not contains_any(upload_to, vocab.scoping_hints + ("%s", "{}")):
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
                if value_name.endswith("objects.all") and not contains_any(evidence, vocab.context_words):
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

    # Client-supplied tenant header used anywhere (middleware/views), not just settings.
    if "x-tenant-id" in lower or "http_x_tenant" in lower:
        findings.append(Finding(
            severity="High",
            rule="TENANT-HEADER",
            path=rel,
            line=1,
            message="Tenant context may be derived from a client-supplied tenant header.",
            evidence="X-Tenant-ID or HTTP_X_TENANT found in file.",
            recommendation="Validate any tenant header against authenticated membership; do not trust raw client-supplied tenant identifiers.",
        ))

    if high_risk and ("@shared_task" in text or "@app.task" in text or "celery" in lower):
        has_orm = ".objects." in text
        has_tenant_context = contains_any(text, vocab.context_words)
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

    if migration and "RunPython" in text and not contains_any(text, ("schema_context", "tenant_context", "migrate_schemas", "get_tenant_model") + vocab.terms):
        findings.append(Finding(
            severity="Medium",
            rule="MIGRATION-RUNPYTHON-NO-TENANT-HINT",
            path=rel,
            line=1,
            message="Data migration uses RunPython without tenant/schema hints.",
            evidence="RunPython found in migration file without tenant/schema context terms.",
            recommendation="Confirm whether this migration runs on public schema, tenant schemas, or both. Test on multiple tenants.",
        ))


def audit_project(root: Path, tenant_terms: Sequence[str] | None = None) -> tuple[ProjectFacts, list[Finding]]:
    findings: list[Finding] = []
    packages = collect_package_facts(root)

    all_text_parts: list[str] = []
    settings_files: list[str] = []
    py_files: list[tuple[Path, str]] = []
    py_count = 0
    test_count = 0
    tenant_terms_in_tests = False

    for path in iter_files(root):
        # Keep all text bounded enough for detection; skip huge locks after package collection.
        if path.stat().st_size > 2_000_000:
            continue
        text = read_text(path)
        all_text_parts.append(text[:100_000])
        if path.suffix == ".py":
            py_count += 1
            py_files.append((path, text))
            if is_test_file(path, root):
                test_count += 1
                if contains_any(text, ("TenantTestCase", "TenantClient", "tenant_a", "tenant_b", "schema_context", "tenant_context", "for_tenant")):
                    tenant_terms_in_tests = True
            if looks_like_settings(path, root, text):
                settings_files.append(relpath(path, root))

    all_text = "\n".join(all_text_parts)
    stack = detect_stack(packages, all_text)

    if tenant_terms:
        effective_terms: tuple[str, ...] = tuple(dict.fromkeys(t.lower() for t in tenant_terms))
    else:
        effective_terms = infer_tenant_terms(all_text, DEFAULT_TENANT_TERMS)
    vocab = build_vocab(effective_terms)

    for path, text in py_files:
        audit_settings(path, root, text, findings)
        audit_python_file(path, root, text, findings, vocab)

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

    # Make a silent gap visible: django-tenants present but no settings module identified,
    # so every DT-* headline check was skipped.
    uses_django_tenants = "django-tenants" in packages or any("django-tenants" in s for s in stack)
    if uses_django_tenants and not settings_files:
        findings.append(Finding(
            severity="High",
            rule="DT-SETTINGS-FILE-NOT-FOUND",
            path=".",
            line=1,
            message="django-tenants detected but no settings-like file was identified; DT-* settings checks were skipped.",
            evidence="No file matched settings/ path or settings markers (INSTALLED_APPS, MIDDLEWARE, DATABASES, ...).",
            recommendation="Point --root at the project root, or confirm the settings module (e.g. config/base.py) is present so backend/router/middleware/SHARED_APPS/TENANT_MODEL checks can run.",
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
        tenant_terms=list(vocab.terms),
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
    lines.append(f"Tenant terms used: {', '.join(facts.tenant_terms) if facts.tenant_terms else '(none)'}")
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
        # Precompute the escaped evidence: a backslash inside an f-string expression is a
        # SyntaxError on Python <= 3.11 (PEP 701 only relaxed this in 3.12).
        evidence = f.evidence[:240].replace("|", "\\|")
        lines.append(f"| {f.severity} | `{f.rule}` | {location} | {msg}<br><br>Evidence: `{evidence}` | {rec} |")

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
    parser.add_argument(
        "--tenant-term",
        "--tenant-field",
        dest="tenant_terms",
        action="append",
        metavar="TERM",
        help=(
            "Noun your project uses for a tenant (e.g. organization, account, workspace, company). "
            "Repeatable: --tenant-term organization --tenant-term workspace. Used by the ORM/scoping "
            "heuristics so a project that never says 'tenant' is still analyzed correctly. If omitted, "
            "a default set (tenant, organization, account, workspace, company, org) is used and extra "
            "terms are inferred from TENANT_MODEL and tenant model class names."
        ),
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: root does not exist: {root}", file=sys.stderr)
        return 2

    facts, findings = audit_project(root, args.tenant_terms)

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
