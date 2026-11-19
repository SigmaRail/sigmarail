"""Import legacy strategy specifications into their PostgreSQL workspace."""

from __future__ import annotations

import hashlib
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.multitenancy.models import Tenant, TenantMembership
from apps.sigmarail_bridge.models import WorkspaceStrategyReference


class Command(BaseCommand):
    help = "Import legacy ClickHouse strategy specifications into an AppTension PostgreSQL workspace."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-slug", required=True)
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--apply", action="store_true", help="Write the imported records to PostgreSQL.")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant_slug"]).first()
        if tenant is None:
            raise CommandError("The target workspace was not found.")

        owner = get_user_model().objects.filter(email__iexact=options["owner_email"]).first()
        if owner is None:
            raise CommandError("The target owner account was not found.")
        if not TenantMembership.objects.filter(user=owner, tenant=tenant, is_accepted=True).exists():
            raise CommandError("The target owner is not an accepted member of the target workspace.")

        try:
            from sigmarail.database import get_client

            client = get_client()
        except Exception as exc:
            raise CommandError(f"Read-only ClickHouse connection unavailable: {exc}") from exc

        imported = skipped = invalid = 0
        try:
            result = client.query(
                "SELECT ir_id, spec_schema_version, title, algorithm_json, notes, pipeline_json, "
                "compiler_version, parent_ir_id, parent_content_hash, mutation_type, changelog_notes, "
                "is_ephemeral FROM strategy_algorithm_specs FINAL ORDER BY created_at ASC",
                settings={"readonly": 1},
            )
            for raw_row in result.result_rows:
                row = dict(zip(result.column_names, raw_row, strict=True))
                if bool(row.get("is_ephemeral")):
                    skipped += 1
                    continue

                ir_id = str(row.get("ir_id") or "").strip()
                raw_spec = row.get("algorithm_json")
                try:
                    spec = json.loads(raw_spec) if isinstance(raw_spec, str) else raw_spec
                    raw_pipeline = row.get("pipeline_json")
                    if isinstance(raw_pipeline, str):
                        pipeline = json.loads(raw_pipeline) if raw_pipeline.strip() else None
                    else:
                        pipeline = raw_pipeline
                except (TypeError, ValueError, json.JSONDecodeError):
                    invalid += 1
                    continue
                if not ir_id or not isinstance(spec, dict) or (pipeline is not None and not isinstance(pipeline, dict)):
                    invalid += 1
                    continue

                canonical = json.dumps(spec, separators=(",", ":"), sort_keys=True)
                content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                existing = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first()
                if existing:
                    # Never overwrite a newer PostgreSQL-authored record during a rerun.
                    if existing.tenant_id == tenant.pk and existing.content_hash == content_hash:
                        skipped += 1
                        continue
                    raise CommandError(
                        f"Strategy {ir_id!r} already exists in PostgreSQL with different ownership or content."
                    )

                imported += 1
                if not options["apply"]:
                    continue

                WorkspaceStrategyReference.objects.create(
                    tenant=tenant,
                    ir_id=ir_id,
                    title=str(row.get("title") or ir_id),
                    spec=spec,
                    pipeline_document=pipeline,
                    notes=str(row.get("notes") or ""),
                    spec_schema_version=int(row.get("spec_schema_version") or 1),
                    compiler_version=str(row.get("compiler_version") or ""),
                    parent_ir_id=str(row.get("parent_ir_id") or ""),
                    parent_content_hash=str(row.get("parent_content_hash") or ""),
                    mutation_type=str(row.get("mutation_type") or "init"),
                    changelog_notes=str(row.get("changelog_notes") or ""),
                    content_hash=content_hash,
                    created_by=owner,
                    owner_user=owner,
                    is_shared=False,
                    is_template=False,
                    synced=True,
                )
        finally:
            client.close()

        verb = "Imported" if options["apply"] else "Would import"
        self.stdout.write(f"{verb} {imported}; already present {skipped}; invalid {invalid}.")
        if not options["apply"]:
            self.stdout.write("Dry run only. Pass --apply to write PostgreSQL records.")
