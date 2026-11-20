"""Audit unmapped workspace records and assign only explicitly approved owners."""

from __future__ import annotations

import json
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.multitenancy.models import Tenant
from apps.sigmarail_bridge.models import (
    WorkspaceBacktestReference,
    WorkspaceDeploymentReference,
    WorkspaceOptimizerReference,
)


OWNED_MODELS = (
    "WorkspaceScreen",
    "WorkspaceStrategyReference",
    "WorkspaceStrategyFrameworkTemplate",
    "WorkspaceBacktestReference",
    "WorkspaceOptimizerReference",
    "WorkspaceDeploymentReference",
    "WorkspaceBrokerAccountReference",
)
CLICKHOUSE_MODELS = {
    "ClickHouseBacktestRun": ("strategy_runs", "run_id"),
    "ClickHouseOptimizerSession": ("strategy_optimizer_sessions", "session_id"),
    "ClickHouseDeployment": ("live_deployments", "deployment_id"),
}


class Command(BaseCommand):
    help = (
        "Report SigmaRail workspace records without a tenant, or assign them using an explicit JSON mapping. "
        "No ownership is inferred from the current user."
    )

    def add_arguments(self, parser):
        parser.add_argument("--mapping-file", help="JSON mapping of model names and record IDs to tenant slugs.")
        parser.add_argument("--apply", action="store_true", help="Apply the explicit mapping (default is preview).")
        parser.add_argument(
            "--include-clickhouse",
            action="store_true",
            help="Read runtime IDs from ClickHouse and report which lack a tenant reference.",
        )
        parser.add_argument(
            "--include-ids",
            action="store_true",
            help="Print up to 20 unassigned record IDs per source.",
        )

    def handle(self, *args, **options):
        mapping_path = options.get("mapping_file")
        if options["apply"] and not mapping_path:
            raise CommandError("--apply requires --mapping-file; ownership is never inferred.")
        if mapping_path and not Path(mapping_path).is_file():
            raise CommandError("The mapping file was not found.")

        self._report_unassigned(include_ids=options["include_ids"])
        if options["include_clickhouse"]:
            self._report_clickhouse_unassigned(include_ids=options["include_ids"])
        if not mapping_path:
            return

        try:
            mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError("The mapping file must contain valid JSON.") from exc
        postgres_assignments, clickhouse_assignments = self._parse_mapping(mapping)
        assignments = postgres_assignments + clickhouse_assignments
        if not assignments:
            self.stdout.write("No assignments in mapping.")
            return

        resolved = []
        for model_name, record_id, tenant_slug in postgres_assignments:
            model = apps.get_model("sigmarail_bridge", model_name)
            record = model.objects.filter(pk=record_id, tenant__isnull=True).first()
            if record is None:
                raise CommandError(f"{model_name} record {record_id!r} is missing or already assigned.")
            tenant = Tenant.objects.filter(slug=tenant_slug).first()
            if tenant is None:
                raise CommandError(f"Target tenant {tenant_slug!r} was not found.")
            if model_name == "WorkspaceStrategyReference" and record.is_template:
                raise CommandError(f"System template {record_id!r} must remain globally owned.")
            resolved.append((record, tenant, model_name))

        clickhouse_rows = self._load_clickhouse_rows(clickhouse_assignments) if clickhouse_assignments else []
        for model_name, record_id, tenant_slug, row in clickhouse_rows:
            tenant = Tenant.objects.filter(slug=tenant_slug).first()
            if tenant is None:
                raise CommandError(f"Target tenant {tenant_slug!r} was not found.")
            existing = self._existing_runtime_reference(model_name, record_id)
            if existing is not None:
                if existing.tenant_id == tenant.pk:
                    continue
                if existing.tenant_id is not None:
                    raise CommandError(
                        f"{model_name} {record_id!r} already belongs to a different tenant."
                    )
                resolved.append((existing, tenant, model_name))
            else:
                resolved.append((self._new_runtime_reference(model_name, record_id, row), tenant, model_name))

        if options["apply"]:
            # Import backtest references first so a deployment can be checked
            # against its approval run before either becomes visible.
            resolved.sort(key=lambda item: self._apply_order(item[2]))
            approved_backtest_ids_by_tenant = set()
            backtests_by_tenant_and_id = {}
            for record, tenant, model_name in resolved:
                if model_name == "ClickHouseBacktestRun":
                    approved_backtest_ids_by_tenant.add((str(record.job_id), tenant.pk))
                    backtests_by_tenant_and_id[(str(record.job_id), tenant.pk)] = record
                elif model_name == "WorkspaceBacktestReference":
                    approved_backtest_ids_by_tenant.add((str(record.job_id), tenant.pk))
                    backtests_by_tenant_and_id[(str(record.job_id), tenant.pk)] = record
                    if record.run_id:
                        approved_backtest_ids_by_tenant.add((str(record.run_id), tenant.pk))
                        backtests_by_tenant_and_id[(str(record.run_id), tenant.pk)] = record
            for record, tenant, model_name in resolved:
                if model_name in {"ClickHouseOptimizerSession", "WorkspaceOptimizerReference"}:
                    best_run_id = str((record.result_summary or {}).get("best_run_id") or "").strip()
                    if best_run_id and not (
                        WorkspaceBacktestReference.objects.filter(tenant=tenant).filter(
                            Q(job_id=best_run_id) | Q(run_id=best_run_id)
                        ).exists()
                        or (best_run_id, tenant.pk) in approved_backtest_ids_by_tenant
                    ):
                        raise CommandError(
                            f"Optimizer session {record.session_id!r} references best run {best_run_id!r}, "
                            "which has not been assigned to this tenant."
                        )
                if model_name in {"ClickHouseDeployment", "WorkspaceDeploymentReference"}:
                    approval_id = str(getattr(record, "approval_run_id", "") or "").strip()
                    if approval_id and not (
                        WorkspaceBacktestReference.objects.filter(
                            tenant=tenant,
                        ).filter(
                            Q(job_id=approval_id) | Q(run_id=approval_id)
                        ).exists()
                        or (approval_id, tenant.pk) in approved_backtest_ids_by_tenant
                    ):
                        raise CommandError(
                            f"Deployment {record.deployment_id!r} references approval run {approval_id!r}, "
                            "which has not been assigned to this tenant."
                        )
                    approval = WorkspaceBacktestReference.objects.filter(tenant=tenant).filter(
                        Q(job_id=approval_id) | Q(run_id=approval_id)
                    ).first()
                    approval = approval or backtests_by_tenant_and_id.get((approval_id, tenant.pk))
                    if approval is not None:
                        if record.ir_id and approval.ir_id and record.ir_id != approval.ir_id:
                            raise CommandError(
                                f"Deployment {record.deployment_id!r} and approval run {approval_id!r} "
                                "refer to different strategies."
                            )
                        record.strategy_content_hash = approval.strategy_content_hash

        if options["apply"]:
            with transaction.atomic():
                for record, tenant, model_name in resolved:
                    if model_name.startswith("ClickHouse"):
                        record.tenant = tenant
                        record.save()
                        continue
                    record.tenant = tenant
                    record.save(update_fields=["tenant", "updated_at"])
            self.stdout.write(self.style.SUCCESS(f"Assigned {len(resolved)} records to their specified tenants."))
        else:
            self.stdout.write(f"Preview only: {len(resolved)} records would be assigned.")
            for record, tenant, model_name in resolved:
                record_id = self._record_identifier(record, model_name)
                self.stdout.write(f"  {model_name} {record_id} -> {tenant.slug}")
            self.stdout.write("Pass --apply to commit these explicit assignments.")

    def _report_unassigned(self, *, include_ids):
        self.stdout.write("Unassigned SigmaRail workspace records (tenant is null):")
        total = 0
        for model_name in OWNED_MODELS:
            model = apps.get_model("sigmarail_bridge", model_name)
            queryset = model.objects.filter(tenant__isnull=True).order_by("pk")
            if model_name == "WorkspaceStrategyReference":
                # Global system templates intentionally have no tenant.
                queryset = queryset.filter(is_template=False)
            count = queryset.count()
            total += count
            self.stdout.write(f"  {model_name}: {count}")
            if include_ids:
                for record in queryset[:20]:
                    self.stdout.write(f"    {record.pk}")
                if count > 20:
                    self.stdout.write(f"    ... {count - 20} more")
        self.stdout.write(f"Total unassigned: {total}")

    def _report_clickhouse_unassigned(self, *, include_ids):
        rows = self._load_clickhouse_identifier_sets()
        reference_models = {
            "ClickHouseBacktestRun": WorkspaceBacktestReference,
            "ClickHouseOptimizerSession": WorkspaceOptimizerReference,
            "ClickHouseDeployment": WorkspaceDeploymentReference,
        }
        for model_name, identifiers in rows.items():
            model = reference_models[model_name]
            references = model.objects.filter(tenant__isnull=False)
            if model_name == "ClickHouseBacktestRun":
                mapped = set(references.values_list("job_id", flat=True))
                mapped.update(references.exclude(run_id__isnull=True).values_list("run_id", flat=True))
            elif model_name == "ClickHouseOptimizerSession":
                mapped = set(references.values_list("session_id", flat=True))
            else:
                mapped = set(references.values_list("deployment_id", flat=True))
            unassigned = sorted(identifiers - mapped)
            self.stdout.write(
                f"  {model_name}: {len(identifiers)} total; {len(unassigned)} without tenant ownership"
            )
            if include_ids:
                for record_id in unassigned[:20]:
                    self.stdout.write(f"    {record_id}")
                if len(unassigned) > 20:
                    self.stdout.write(f"    ... {len(unassigned) - 20} more")

    def _load_clickhouse_identifier_sets(self):
        if not settings.SIGMARAIL_CLICKHOUSE_ENABLED:
            raise CommandError("ClickHouse inventory requires SIGMARAIL_CLICKHOUSE_ENABLED.")
        import clickhouse_connect

        client = clickhouse_connect.get_client(
            host=settings.SIGMARAIL_CLICKHOUSE_HOST,
            port=settings.SIGMARAIL_CLICKHOUSE_HTTP_PORT,
            username=settings.SIGMARAIL_CLICKHOUSE_USER,
            password=settings.SIGMARAIL_CLICKHOUSE_PASSWORD,
            database=settings.SIGMARAIL_CLICKHOUSE_DATABASE,
            secure=settings.SIGMARAIL_CLICKHOUSE_SECURE,
            connect_timeout=10,
            settings={"readonly": 1},
        )
        results = {}
        try:
            for model_name, (table, key) in CLICKHOUSE_MODELS.items():
                # Identifiers are selected only from the fixed CLICKHOUSE_MODELS allowlist.
                result = client.query(f"SELECT {key} FROM {table} FINAL")  # noqa: S608
                results[model_name] = {str(row[0]) for row in result.result_rows if row and row[0]}
        finally:
            client.close()
        return results

    @staticmethod
    def _record_identifier(record, model_name):
        if model_name in {"WorkspaceBacktestReference", "ClickHouseBacktestRun"}:
            return getattr(record, "job_id", None) or record.pk
        if model_name in {"WorkspaceOptimizerReference", "ClickHouseOptimizerSession"}:
            return getattr(record, "session_id", None) or record.pk
        if model_name in {"WorkspaceDeploymentReference", "ClickHouseDeployment"}:
            return getattr(record, "deployment_id", None) or record.pk
        return record.pk

    @staticmethod
    def _parse_mapping(mapping):
        if not isinstance(mapping, dict):
            raise CommandError("The mapping root must be an object keyed by model name.")
        postgres_assignments = []
        clickhouse_assignments = []
        seen = set()
        for model_name, records in mapping.items():
            if model_name not in {*OWNED_MODELS, *CLICKHOUSE_MODELS}:
                raise CommandError(f"Unsupported model in mapping: {model_name!r}.")
            if not isinstance(records, list):
                raise CommandError(f"Mapping for {model_name} must be a list.")
            for item in records:
                if not isinstance(item, dict):
                    raise CommandError(f"Each {model_name} mapping must be an object.")
                record_key = CLICKHOUSE_MODELS[model_name][1] if model_name in CLICKHOUSE_MODELS else "id"
                record_id = str(item.get(record_key) or "").strip()
                tenant_slug = str(item.get("tenant_slug") or "").strip()
                key = (model_name, record_id)
                if not record_id or not tenant_slug or key in seen:
                    raise CommandError(f"Invalid or duplicate mapping for {model_name}.")
                seen.add(key)
                assignment = (model_name, record_id, tenant_slug)
                if model_name in CLICKHOUSE_MODELS:
                    clickhouse_assignments.append(assignment)
                else:
                    postgres_assignments.append(assignment)
        return postgres_assignments, clickhouse_assignments

    @staticmethod
    def _existing_runtime_reference(model_name, record_id):
        if model_name == "ClickHouseBacktestRun":
            return WorkspaceBacktestReference.objects.filter(Q(job_id=record_id) | Q(run_id=record_id)).first()
        if model_name == "ClickHouseOptimizerSession":
            return WorkspaceOptimizerReference.objects.filter(session_id=record_id).first()
        return WorkspaceDeploymentReference.objects.filter(deployment_id=record_id).first()

    @staticmethod
    def _new_runtime_reference(model_name, record_id, row):
        if model_name == "ClickHouseBacktestRun":
            ir_id = str(row.get("ir_id") or "")
            raw_parameters = row.get("parameters")
            try:
                parameters = json.loads(raw_parameters) if isinstance(raw_parameters, str) else {}
            except json.JSONDecodeError:
                parameters = {"raw_parameters": raw_parameters}
            configuration = parameters if isinstance(parameters, dict) else {"parameters": parameters}
            configuration.update(
                {
                    "period_start": str(row.get("period_start") or ""),
                    "period_end": str(row.get("period_end") or ""),
                    "legacy_run_timestamp": str(row.get("run_timestamp") or ""),
                }
            )
            return WorkspaceBacktestReference(
                job_id=record_id,
                run_id=record_id,
                ir_id=ir_id,
                strategy_content_hash=str(row.get("ir_content_hash") or "").strip(),
                configuration=configuration,
                status="completed",
            )
        if model_name == "ClickHouseOptimizerSession":
            configuration = json.loads(json.dumps(row, default=str))
            return WorkspaceOptimizerReference(
                session_id=record_id,
                base_ir_id=str(row.get("base_ir_id") or ""),
                configuration=configuration,
                status=str(row.get("status") or "unknown")[:24],
                result_summary={
                    key: row.get(key)
                    for key in ("best_run_id", "best_score", "best_parameters", "total_combinations")
                },
            )
        raw_parameters = row.get("parameters")
        try:
            parameters = json.loads(raw_parameters) if isinstance(raw_parameters, str) else {}
        except json.JSONDecodeError:
            parameters = {"raw_parameters": raw_parameters}
        return WorkspaceDeploymentReference(
            deployment_id=record_id,
            ir_id=str(row.get("ir_id") or ""),
            approval_run_id=str(row.get("approval_backtest_run_id") or ""),
            configuration={
                "lean_environment": str(row.get("lean_environment") or ""),
                "brokerage": str(row.get("brokerage") or ""),
                "started_at": str(row.get("started_at") or ""),
                "parameters": parameters,
                "legacy_created_at": str(row.get("created_at") or ""),
            },
            status=str(row.get("status") or "unknown")[:24],
            stopped_at=row.get("stopped_at"),
        )

    @staticmethod
    def _apply_order(model_name):
        if model_name in {"ClickHouseBacktestRun", "WorkspaceBacktestReference"}:
            return 0
        if model_name in {"ClickHouseOptimizerSession", "WorkspaceOptimizerReference"}:
            return 1
        return 2

    def _load_clickhouse_rows(self, assignments):
        if not settings.SIGMARAIL_CLICKHOUSE_ENABLED:
            raise CommandError("ClickHouse import requires SIGMARAIL_CLICKHOUSE_ENABLED.")
        import clickhouse_connect

        client = clickhouse_connect.get_client(
            host=settings.SIGMARAIL_CLICKHOUSE_HOST,
            port=settings.SIGMARAIL_CLICKHOUSE_HTTP_PORT,
            username=settings.SIGMARAIL_CLICKHOUSE_USER,
            password=settings.SIGMARAIL_CLICKHOUSE_PASSWORD,
            database=settings.SIGMARAIL_CLICKHOUSE_DATABASE,
            secure=settings.SIGMARAIL_CLICKHOUSE_SECURE,
            connect_timeout=10,
            settings={"readonly": 1},
        )
        select_columns = {
            "ClickHouseBacktestRun": (
                "run_id, ir_id, ir_content_hash, parameters, period_start, period_end, run_timestamp"
            ),
            "ClickHouseOptimizerSession": (
                "session_id, base_ir_id, title, objective, param_x_name, param_x_values, param_y_name, "
                "param_y_values, total_combinations, status, best_run_id, best_score, best_parameters, "
                "strategy_type, oos_days, constraints_json, max_concurrent, created_at, updated_at"
            ),
            "ClickHouseDeployment": (
                "deployment_id, ir_id, lean_environment, brokerage, status, started_at, stopped_at, "
                "approval_backtest_run_id, parameters, created_at"
            ),
        }
        loaded = []
        try:
            for model_name, record_id, tenant_slug in assignments:
                table, key = CLICKHOUSE_MODELS[model_name]
                # Table, selected fields, and key are fixed allowlisted identifiers;
                # the runtime identifier value remains a bound query parameter.
                result = client.query(  # noqa: S608
                    f"SELECT {select_columns[model_name]} FROM {table} FINAL "  # noqa: S608
                    f"WHERE {key} = {{record_id:String}} LIMIT 1",  # noqa: S608
                    parameters={"record_id": record_id},
                    settings={"readonly": 1},
                )
                if not result.result_rows:
                    raise CommandError(f"{model_name} record {record_id!r} was not found in ClickHouse.")
                row = dict(zip(result.column_names, result.result_rows[0], strict=True))
                loaded.append((model_name, record_id, tenant_slug, row))
        finally:
            client.close()
        return loaded
