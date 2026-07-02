#!/usr/bin/env python3
"""
Conservative scaffold helper for django-tenants.

It creates a tenant app with tenant/domain models, admin registration, a provisioning
management command, a smoke test, and a settings snippet. It does not edit your
settings automatically.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from textwrap import dedent
from typing import Sequence


def snake_case(name: str) -> str:
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def validate_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"{label} must be a valid Python identifier: {value!r}")


def validate_app_path(value: str) -> None:
    for part in value.split("."):
        validate_identifier(part, "app path component")


def write_file(path: Path, content: str, *, force: bool) -> bool:
    if path.exists() and not force:
        print(f"skip existing: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote: {path}")
    return True


def build_files(app: str, tenant_model: str, domain_model: str) -> dict[str, str]:
    app_config_name = "".join(part.capitalize() for part in app.split(".")) + "Config"
    # Django derives the app label from the last dotted segment of the app path, so a
    # dotted --app (e.g. platform.tenants) has label "tenants". TENANT_MODEL/
    # TENANT_DOMAIN_MODEL must be "<app_label>.<ModelName>", never the full dotted path.
    app_label = app.split(".")[-1]
    tenant_var = snake_case(tenant_model)

    files: dict[str, str] = {}
    files["__init__.py"] = ""
    files["apps.py"] = dedent(f'''
        from django.apps import AppConfig


        class {app_config_name}(AppConfig):
            default_auto_field = "django.db.models.BigAutoField"
            name = "{app}"
    ''').lstrip()

    files["models.py"] = dedent(f'''
        from django.core.validators import RegexValidator
        from django.db import models
        from django_tenants.models import DomainMixin, TenantMixin


        schema_name_validator = RegexValidator(
            regex=r"^[a-z][a-z0-9_]*$",
            message="Schema names must start with a lowercase letter and contain only lowercase letters, numbers, and underscores.",
        )


        class {tenant_model}(TenantMixin):
            """Platform tenant.

            This model lives in the public schema. Tenant-owned application data lives in
            each tenant schema when using django-tenants.
            """

            name = models.CharField(max_length=255)
            slug = models.SlugField(unique=True)
            schema_name = models.CharField(max_length=63, unique=True, validators=[schema_name_validator])
            is_active = models.BooleanField(default=True)
            on_trial = models.BooleanField(default=True)
            paid_until = models.DateField(null=True, blank=True)
            created_at = models.DateTimeField(auto_now_add=True)
            updated_at = models.DateTimeField(auto_now=True)

            # Create schema on save. Keep physical drop disabled unless your offboarding
            # runbook explicitly approves destructive deletion.
            auto_create_schema = True
            auto_drop_schema = False

            class Meta:
                ordering = ["name"]

            def __str__(self) -> str:
                return self.name


        class {domain_model}(DomainMixin):
            """Domain mapping for a tenant.

            DomainMixin provides domain, tenant, and is_primary fields.
            Add domain verification fields here before supporting custom domains.
            """

            pass
    ''').lstrip()

    files["admin.py"] = dedent(f'''
        from django.contrib import admin
        from django_tenants.admin import TenantAdminMixin

        from .models import {domain_model}, {tenant_model}


        @admin.register({tenant_model})
        class {tenant_model}Admin(TenantAdminMixin, admin.ModelAdmin):
            list_display = ("name", "schema_name", "slug", "is_active", "on_trial", "paid_until", "created_at")
            list_filter = ("is_active", "on_trial")
            search_fields = ("name", "slug", "schema_name")
            readonly_fields = ("created_at", "updated_at")


        @admin.register({domain_model})
        class {domain_model}Admin(admin.ModelAdmin):
            list_display = ("domain", "tenant", "is_primary")
            list_filter = ("is_primary",)
            search_fields = ("domain", "tenant__name", "tenant__schema_name")
    ''').lstrip()

    files["management/__init__.py"] = ""
    files["management/commands/__init__.py"] = ""
    files["management/commands/provision_tenant.py"] = dedent(f'''
        import re

        from django.core.management.base import BaseCommand, CommandError

        from {app}.models import {domain_model}, {tenant_model}


        class Command(BaseCommand):
            help = "Provision a django-tenants tenant and primary domain."

            def add_arguments(self, parser):
                parser.add_argument("--schema", required=True, help="PostgreSQL schema name, e.g. acme")
                parser.add_argument("--domain", required=True, help="Tenant domain without scheme, e.g. acme.localhost")
                parser.add_argument("--name", required=True, help="Display name, e.g. Acme Inc")
                parser.add_argument("--slug", help="Public slug. Defaults to schema.")
                parser.add_argument("--active", action="store_true", help="Mark tenant active immediately.")

            def handle(self, *args, **options):
                # No @transaction.atomic here: with auto_create_schema=True, saving the
                # tenant creates the schema and runs its migrations outside this
                # transaction, so wrapping handle() conflicts with it (and migrations
                # using CREATE INDEX CONCURRENTLY cannot run inside a transaction block).
                schema_name = options["schema"].strip().lower()
                if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema_name) or schema_name.startswith("pg_"):
                    raise CommandError(
                        f"Invalid schema name {{schema_name!r}}: must match "
                        "^[a-z_][a-z0-9_]*$ and must not start with 'pg_'."
                    )
                domain_name = options["domain"].strip().lower().removeprefix("http://").removeprefix("https://").rstrip("/")
                slug = options.get("slug") or schema_name

                if {tenant_model}.objects.filter(schema_name=schema_name).exists():
                    raise CommandError(f"Tenant schema already exists: {{schema_name}}")
                if {domain_model}.objects.filter(domain=domain_name).exists():
                    raise CommandError(f"Domain already exists: {{domain_name}}")

                {tenant_var} = {tenant_model}.objects.create(
                    schema_name=schema_name,
                    name=options["name"],
                    slug=slug,
                    is_active=bool(options["active"]),
                )
                {domain_model}.objects.create(domain=domain_name, tenant={tenant_var}, is_primary=True)

                self.stdout.write(self.style.SUCCESS(
                    f"Provisioned tenant schema={{schema_name}} domain={{domain_name}} active={{{tenant_var}.is_active}}"
                ))
                self.stdout.write("Next: create owner/membership/default data in tenant context before exposing tenant to users.")
    ''').lstrip()

    files["tests/__init__.py"] = ""
    files["tests/test_tenant_smoke.py"] = dedent(f'''
        from django_tenants.test.cases import TenantTestCase
        from django_tenants.test.client import TenantClient


        class {tenant_model}SmokeTests(TenantTestCase):
            @classmethod
            def setup_tenant(cls, tenant):
                tenant.name = "Test Tenant"
                tenant.slug = "test-tenant"
                tenant.is_active = True
                return tenant

            def setUp(self):
                super().setUp()
                self.client = TenantClient(self.tenant)

            def test_test_tenant_is_available(self):
                assert self.tenant.schema_name
                assert self.client is not None
    ''').lstrip()

    files["settings_django_tenants_snippet.py"] = dedent(f'''
        # Copy/adapt this into your real settings module. Do not import this file directly
        # unless you intentionally manage settings composition this way.

        DATABASES = {{
            "default": {{
                "ENGINE": "django_tenants.postgresql_backend",
                # "NAME": env("POSTGRES_DB"),
                # "USER": env("POSTGRES_USER"),
                # "PASSWORD": env("POSTGRES_PASSWORD"),
                # "HOST": env("POSTGRES_HOST", default="localhost"),
                # "PORT": env("POSTGRES_PORT", default="5432"),
            }}
        }}

        DATABASE_ROUTERS = (
            "django_tenants.routers.TenantSyncRouter",
        )

        MIDDLEWARE = (
            "django_tenants.middleware.main.TenantMainMiddleware",
            # ... existing middleware after tenant middleware ...
        )

        SHARED_APPS = (
            "django_tenants",
            "{app}",
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.admin",
            "django.contrib.staticfiles",
            # global/shared apps here
        )

        TENANT_APPS = (
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "django.contrib.sessions",
            "django.contrib.messages",
            "django.contrib.admin",
            "django.contrib.staticfiles",
            # tenant-owned apps here
        )

        INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

        TENANT_MODEL = "{app_label}.{tenant_model}"
        TENANT_DOMAIN_MODEL = "{app_label}.{domain_model}"

        # Optional but recommended for tenant-specific cache data:
        # CACHES["default"]["KEY_FUNCTION"] = "django_tenants.cache.make_key"
        # CACHES["default"]["REVERSE_KEY_FUNCTION"] = "django_tenants.cache.reverse_key"
    ''').lstrip()

    return files


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a conservative django-tenants app scaffold.")
    parser.add_argument("--root", default=".", help="Django project root. Default: current directory.")
    parser.add_argument("--app", default="customers", help="Python app path to create, e.g. customers or apps.tenants.")
    parser.add_argument("--tenant-model", default="Client", help="Tenant model class name. Default: Client.")
    parser.add_argument("--domain-model", default="Domain", help="Domain model class name. Default: Domain.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args(argv)

    try:
        validate_app_path(args.app)
        validate_identifier(args.tenant_model, "tenant model")
        validate_identifier(args.domain_model, "domain model")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    root = Path(args.root).resolve()
    app_dir = root.joinpath(*args.app.split("."))
    files = build_files(args.app, args.tenant_model, args.domain_model)
    for relative, content in files.items():
        write_file(app_dir / relative, content, force=args.force)

    print("\nNext steps:")
    print("1. Add django-tenants to dependencies and install.")
    print(f"2. Copy/adapt {app_dir / 'settings_django_tenants_snippet.py'} into your real settings.")
    print("3. Run: python manage.py makemigrations")
    print("4. Run: python manage.py migrate_schemas --shared")
    print("5. Provision public tenant and first real tenant.")
    print("6. Add owner/membership/default-data flow and tenant isolation tests before production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
