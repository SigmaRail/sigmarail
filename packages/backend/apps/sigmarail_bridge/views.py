from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import uuid

from django.db import IntegrityError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.http.request import RawPostDataException
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from graphql_relay import from_global_id
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.multitenancy.middleware import get_current_tenant_with_membership_check
from .models import (
    WorkspaceBrokerAccountReference,
    WorkspaceBacktestReference,
    WorkspaceDeploymentReference,
    WorkspaceOptimizerReference,
    WorkspaceScreen,
    WorkspaceStrategyReference,
)
from .in_process_api import InProcessDispatchError, dispatch_api_request


class RuntimeIdentityView(APIView):
    """Expose non-secret build identity so a running API can certify its source."""

    def get(self, request):
        return Response(
            {
                "service": "sigmarail-api",
                "revision": os.environ.get("SIGMARAIL_BUILD_REVISION", "unknown"),
                "branch": os.environ.get("SIGMARAIL_BUILD_BRANCH", "unknown"),
                "source_tree": os.environ.get("SIGMARAIL_BUILD_TREE", "unknown"),
                "container": socket.gethostname(),
                "image": os.environ.get("SIGMARAIL_IMAGE_ID", "unknown"),
                "ports": {
                    "container": os.environ.get("SIGMARAIL_RUNTIME_API_CONTAINER_PORT", "5001"),
                    "published": os.environ.get("SIGMARAIL_RUNTIME_API_HOST_PORT", "unknown"),
                },
                "tailscale": {
                    "host": os.environ.get("SIGMARAIL_RUNTIME_TAILSCALE_HOST", "unknown"),
                    "port": os.environ.get("SIGMARAIL_RUNTIME_TAILSCALE_PORT", "unknown"),
                    "target": os.environ.get("SIGMARAIL_RUNTIME_TAILSCALE_TARGET", "unknown"),
                },
            }
        )


def _workspace_for_request(request: Request):
    relay_workspace_id = request.headers.get("X-Tenant-ID", "").strip()
    if not relay_workspace_id:
        return None, Response({"detail": "An active workspace is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        workspace_type, workspace_id = from_global_id(relay_workspace_id)
    except (TypeError, ValueError):
        return None, Response({"detail": "The active workspace ID is invalid."}, status=status.HTTP_400_BAD_REQUEST)
    if workspace_type != "TenantType" or not workspace_id:
        return None, Response({"detail": "The active workspace ID is invalid."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        workspace = get_current_tenant_with_membership_check(
            workspace_id,
            request.user,
            request._request,
        )
    except (TypeError, ValueError, ValidationError):
        workspace = None
    if workspace is None:
        return None, Response({"detail": "You are not a member of this workspace."}, status=status.HTTP_403_FORBIDDEN)
    return workspace, None


def _serialize_workspace_screen(screen: WorkspaceScreen) -> dict:
    return {
        "id": str(screen.id),
        "name": screen.name,
        "description": screen.description,
        "spec": screen.spec,
        "is_system": False,
        "is_shared": screen.is_shared,
        "category": "Workspace",
        "source_template_id": screen.source_template_id,
        "created_at": screen.created_at.isoformat() if screen.created_at else None,
        "updated_at": screen.updated_at.isoformat() if screen.updated_at else None,
    }


def _forwarded_request_body(request: Request) -> bytes | None:
    """Return a request body without rereading a stream already parsed by DRF."""
    raw_request = request._request
    raw_body = getattr(raw_request, "_body", None)
    if raw_body is not None:
        return raw_body or None

    try:
        body = raw_request.body
    except RawPostDataException:
        data = request.data
        content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
        if content_type == "application/json" or content_type.endswith("+json"):
            return json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if hasattr(data, "urlencode"):
            return data.urlencode().encode("utf-8") or None
        if isinstance(data, dict):
            from urllib.parse import urlencode

            return urlencode(data, doseq=True).encode("utf-8") or None
        return None
    return body or None


def _save_broker_account_metadata(reference, payload: dict, *, overwrite: bool) -> None:
    """Persist only the non-secret account fields owned by AppTension."""
    importing_legacy_profile = not reference.provider
    fields = {
        "provider": (32, ""),
        "data_provider": (32, ""),
        "environment": (16, "paper"),
        "display_name": (80, ""),
        "account_identifier": (128, ""),
    }
    updates = []
    for field, (limit, default) in fields.items():
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        value = value.strip()[:limit] or default
        if overwrite or not getattr(reference, field):
            if getattr(reference, field) != value:
                setattr(reference, field, value)
                updates.append(field)
    active = payload.get("active")
    if isinstance(active, bool) and (overwrite or importing_legacy_profile) and reference.active != active:
        reference.active = active
        updates.append("active")
    if updates:
        reference.save(update_fields=[*updates, "updated_at"])


def _serialize_workspace_broker_account(profile: dict, reference) -> dict:
    """Use PostgreSQL account metadata while retaining live vault status."""
    return {
        **profile,
        "provider": reference.provider or profile.get("provider", ""),
        "data_provider": reference.data_provider or profile.get("data_provider", ""),
        "environment": reference.environment,
        "display_name": reference.display_name or profile.get("display_name", ""),
        "account_identifier": reference.account_identifier or profile.get("account_identifier", ""),
        "active": reference.active,
        "updated_at": reference.updated_at.isoformat() if reference.updated_at else profile.get("updated_at"),
    }


def _legacy_shared_screens(request: Request) -> list[dict]:
    response = _dispatch_domain_api("GET", "/api/screens/saved", request=request)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("screens"), list):
        raise ValueError("Shared screen catalog response has an invalid shape")
    records = payload["screens"]
    shared = []
    for record in records:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("id"), (str, int))
            or not isinstance(record.get("name"), str)
            or not isinstance(record.get("spec"), dict)
        ):
            raise ValueError("Shared screen catalog contains an invalid screen")
        item = dict(record)
        if not item.get("is_system"):
            item["id"] = f"shared:{item.get('id', '')}"
            item["is_shared"] = True
            item["category"] = "Shared"
        shared.append(item)
    return shared


def _dispatch_domain_api(
    method: str,
    path: str,
    *,
    query: str = "",
    content: bytes | None = None,
    request: Request | None = None,
):
    headers = {}
    user = None
    session = None
    if request is not None:
        headers = {
            name: request.headers[name]
            for name in ("accept", "content-type", "x-tenant-id")
            if name in request.headers
        }
        user = request.user
        session = getattr(request._request, "session", None)
    return dispatch_api_request(
        method,
        path,
        query=query,
        content=content,
        user=user,
        session=session,
        headers=headers,
    )


def _domain_json_response(upstream) -> Response:
    try:
        payload = upstream.json()
    except ValueError:
        return Response(
            {"detail": "SigmaRail API returned an invalid JSON response."}, status=status.HTTP_502_BAD_GATEWAY
        )
    return Response(payload, status=upstream.status_code)


def _strategy_json(reference: WorkspaceStrategyReference) -> dict:
    """Serialize an authored strategy without consulting the analytical store."""
    algorithm_json = json.dumps(reference.spec or {}, separators=(",", ":"), sort_keys=True)
    pipeline_json = (
        json.dumps(reference.pipeline_document, separators=(",", ":"), sort_keys=True)
        if isinstance(reference.pipeline_document, dict)
        else ""
    )
    try:
        from screens.backtest import _parse_framework_slots
        from screens.backtest_jobs import _extract_screener_summary

        slot_summary = _parse_framework_slots(algorithm_json)
        screener_summary = _extract_screener_summary(algorithm_json)
    except Exception:
        slot_summary = {}
        screener_summary = {"has_screener": False, "source": None, "rules_count": 0, "order_by": None}
    return {
        "ir_id": reference.ir_id,
        "title": reference.title or reference.ir_id,
        "spec_schema_version": reference.spec_schema_version or 1,
        "notes": reference.notes,
        "category": reference.category or ("Custom Template" if reference.is_template else "Custom Spec"),
        "is_system": False,
        "is_template": reference.is_template,
        "has_pipeline": bool(reference.pipeline_document),
        "schema_status": "modern" if reference.pipeline_document else "legacy",
        "created_at": reference.created_at.isoformat() if reference.created_at else None,
        "updated_at": reference.updated_at.isoformat() if reference.updated_at else None,
        "algorithm_json": algorithm_json,
        "spec": reference.spec or {},
        "pipeline_document": reference.pipeline_document,
        "pipeline_json": pipeline_json,
        "ir_content_hash": reference.content_hash or hashlib.sha256(algorithm_json.encode("utf-8")).hexdigest(),
        "compiler_version": reference.compiler_version,
        "lineage": {
            "parent_ir_id": reference.parent_ir_id or None,
            "parent_content_hash": reference.parent_content_hash or None,
            "mutation_type": reference.mutation_type or "init",
            "changelog_notes": reference.changelog_notes,
            "author_agent": "user",
        },
        "is_shared": reference.is_shared,
        "screener_summary": screener_summary,
        **slot_summary,
    }


def _accessible_strategy(workspace, user, ir_id: str):
    reference = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first()
    if reference is None or reference.tenant_id != workspace.id:
        return None
    if reference.owner_user_id != user.id and not reference.is_shared and not reference.is_template:
        return None
    if not isinstance(reference.spec, dict):
        return None
    return reference


class WorkspaceStrategySpecsView(APIView):
    """Authoritative strategy catalog and saves in AppTension PostgreSQL."""

    def get(self, request: Request) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        try:
            limit = max(1, min(int(request.query_params.get("limit") or 50), 200))
        except (TypeError, ValueError):
            return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        search = request.query_params.get("search", "").strip().casefold()
        references = WorkspaceStrategyReference.objects.filter(tenant=workspace).filter(
            Q(owner_user=request.user) | Q(is_shared=True) | Q(is_template=True)
        ).exclude(spec__isnull=True)
        records = [_strategy_json(reference) for reference in references]
        if search:
            records = [
                record for record in records
                if search in " ".join((record["ir_id"], record["title"], record["notes"], record["category"])).casefold()
            ]
        template_filter = request.query_params.get("is_template")
        if template_filter is not None:
            want_templates = template_filter.casefold() in {"true", "1", "yes"}
            records = [record for record in records if record["is_template"] is want_templates]
        records.sort(key=lambda record: (record["created_at"] or "", record["ir_id"]), reverse=True)
        return Response({"specs": records[:limit], "count": min(len(records), limit), "total": len(records)})

    def post(self, request: Request) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        ir_id = str(body.get("ir_id") or "").strip()
        title = str(body.get("title") or "").strip()
        if not ir_id or "/" in ir_id:
            return Response(
                {"detail": "ir_id is required and cannot contain slashes."}, status=status.HTTP_400_BAD_REQUEST
            )
        if not title:
            return Response({"detail": "title is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(body.get("spec"), dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)

        reference = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first()
        if reference is not None:
            if reference.tenant_id != workspace.id:
                return Response({"detail": "This strategy belongs to another workspace."}, status=status.HTTP_409_CONFLICT)
            if reference.owner_user_id != request.user.id and not reference.is_shared:
                return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
            if reference.is_shared:
                return Response(
                    {
                        "detail": "Shared strategies are read-only. Fork the strategy to save your own copy.",
                        "code": "strategy_shared_read_only",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        pipeline = body.get("pipeline_document")
        if pipeline is not None and not isinstance(pipeline, dict):
            return Response({"detail": "pipeline_document must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        if reference is not None and reference.is_shared:
            return Response({"detail": "Shared strategies are read-only. Fork the strategy to save a copy.",
                             "code": "strategy_shared_read_only"}, status=status.HTTP_403_FORBIDDEN)
        raw_spec = json.dumps(body["spec"], separators=(",", ":"), sort_keys=True)
        content_hash = hashlib.sha256(raw_spec.encode("utf-8")).hexdigest()
        expected_hash = str(body.get("expected_hash") or "").strip()
        if reference is not None and expected_hash and reference.content_hash and expected_hash != reference.content_hash:
            return Response({"detail": "expected_hash mismatch", "ir_content_hash": reference.content_hash,
                             "code": "conflict"}, status=status.HTTP_409_CONFLICT)
        fork_parent = reference
        if reference is not None and (
            bool(body.get("force_new_version"))
            or WorkspaceBacktestReference.objects.filter(ir_id=ir_id).exists()
        ):
            version = 2
            while WorkspaceStrategyReference.objects.filter(ir_id=f"{ir_id}-v{version}").exists():
                version += 1
            ir_id = f"{ir_id}-v{version}"
            reference = None
        is_new = reference is None
        try:
            with transaction.atomic():
                if reference is None:
                    reference = WorkspaceStrategyReference(
                        tenant=workspace, created_by=request.user, owner_user=request.user, ir_id=ir_id,
                    )
                    if fork_parent is not None:
                        reference.parent_ir_id = fork_parent.ir_id
                        reference.parent_content_hash = fork_parent.content_hash
                        reference.mutation_type = "fork"
                reference.title = title
                reference.spec = body["spec"]
                reference.pipeline_document = pipeline
                reference.notes = str(body.get("notes") or "")
                reference.category = str(body.get("category") or "").strip()
                reference.tags = body.get("tags") if isinstance(body.get("tags"), list) else []
                reference.spec_schema_version = int(body.get("spec_schema_version") or 1)
                reference.content_hash = content_hash
                reference.compiler_version = str(body.get("compiler_version") or "")
                if fork_parent is None:
                    reference.parent_ir_id = str(body.get("parent_ir_id") or "")
                    reference.parent_content_hash = str(body.get("parent_content_hash") or "")
                    reference.mutation_type = str(body.get("mutation_type") or "init")
                elif reference.mutation_type != "fork":
                    reference.mutation_type = str(body.get("mutation_type") or "edit")
                reference.changelog_notes = str(body.get("changelog_notes") or "")
                reference.is_template = bool(body.get("is_template", False))
                reference.is_shared = False
                reference.synced = True
                reference.save()
        except IntegrityError:
            return Response({"detail": "This strategy ID is already owned by another workspace."},
                            status=status.HTTP_409_CONFLICT)
        result = _strategy_json(reference)
        return Response(result, status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK)


class WorkspaceStrategySpecDetailView(APIView):
    """Read a strategy version from its PostgreSQL source of truth."""

    def get(self, request: Request, ir_id: str) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        reference = _accessible_strategy(workspace, request.user, ir_id)
        if reference is None:
            return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_strategy_json(reference))


class WorkspaceSavedScreensView(APIView):
    """User-owned screen CRUD with shared legacy screens kept read-only."""

    def get(self, request: Request) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        owned = [
            _serialize_workspace_screen(screen)
            for screen in WorkspaceScreen.objects.filter(tenant=workspace).filter(
                Q(owner_user=request.user) | Q(is_shared=True)
            )
        ]
        from .screen_templates import packaged_universe_screens

        system_screens = packaged_universe_screens()
        try:
            shared = _legacy_shared_screens(request)
        except (InProcessDispatchError, ValueError):
            # Built-in templates belong to this application. Keep them and
            # workspace-owned screens usable when the transitional service that
            # supplies legacy shared screens is unavailable.
            records = system_screens + owned
            return Response(
                {
                    "screens": records,
                    "count": len(records),
                    "shared_catalog_available": False,
                    "shared_catalog_warning": (
                        "Legacy shared saved screens are temporarily unavailable. "
                        "Built-in templates and your workspace screens are available."
                    ),
                }
            )
        # The packaged active catalog is authoritative for built-ins; retain
        # legacy custom/shared screens, but don't surface stale system entries.
        legacy_shared = [screen for screen in shared if not screen.get("is_system")]
        records = system_screens + legacy_shared + owned
        return Response(
            {
                "screens": records,
                "count": len(records),
                "shared_catalog_available": True,
            }
        )

    def post(self, request: Request) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        name = str(body.get("name") or "").strip()
        spec = body.get("spec")
        if not name:
            return Response({"detail": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            screen = WorkspaceScreen.objects.create(
                tenant=workspace,
                created_by=request.user,
                owner_user=request.user,
                name=name,
                description=str(body.get("description") or "").strip(),
                spec=spec,
                source_template_id=str(body.get("source_template_id") or "").strip(),
            )
        except IntegrityError:
            return Response(
                {"detail": f"A screen named {name!r} already exists in this workspace."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize_workspace_screen(screen), status=status.HTTP_201_CREATED)


class WorkspaceSavedScreenDetailView(APIView):
    """Update/delete a workspace screen; saving a shared screen creates a copy."""

    def put(self, request: Request, screen_id: str) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        name = str(body.get("name") or "").strip()
        spec = body.get("spec")
        if not name:
            return Response({"detail": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(spec, dict):
            return Response({"detail": "spec must be an object"}, status=status.HTTP_400_BAD_REQUEST)

        if screen_id.startswith("shared:"):
            return WorkspaceSavedScreensView().post(request)

        try:
            screen = WorkspaceScreen.objects.get(id=screen_id, tenant=workspace, owner_user=request.user)
        except (WorkspaceScreen.DoesNotExist, ValueError, ValidationError):
            return Response({"detail": "Saved screen not found."}, status=status.HTTP_404_NOT_FOUND)
        screen.name = name
        screen.spec = spec
        screen.description = str(body.get("description") or screen.description).strip()
        screen.source_template_id = str(body.get("source_template_id") or screen.source_template_id).strip()
        try:
            screen.save(update_fields=["name", "spec", "description", "source_template_id", "updated_at"])
        except IntegrityError:
            return Response(
                {"detail": f"A screen named {name!r} already exists in this workspace."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize_workspace_screen(screen))

    def delete(self, request: Request, screen_id: str) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        if screen_id.startswith("shared:"):
            return Response({"detail": "Shared screens cannot be deleted."}, status=status.HTTP_403_FORBIDDEN)
        try:
            screen = WorkspaceScreen.objects.get(id=screen_id, tenant=workspace, owner_user=request.user)
        except (WorkspaceScreen.DoesNotExist, ValueError, ValidationError):
            return Response({"detail": "Saved screen not found."}, status=status.HTTP_404_NOT_FOUND)
        screen.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DomainAPIRouteView(APIView):
    """Authenticated AppTension route for existing in-process domain views."""

    request_headers = ("accept", "content-type", "if-match", "if-none-match", "x-tenant-id")
    response_headers = ("content-type", "cache-control", "etag", "last-modified", "retry-after")

    def get(self, request: Request, **kwargs) -> HttpResponse:
        return self._dispatch(request)

    def head(self, request: Request, **kwargs) -> HttpResponse:
        return self._dispatch(request)

    def options(self, request: Request, **kwargs) -> HttpResponse:
        return self._dispatch(request)

    def post(self, request: Request, **kwargs) -> HttpResponse:
        return self._dispatch(request)

    def put(self, request: Request, **kwargs) -> HttpResponse:
        return self._dispatch(request)

    def patch(self, request: Request, **kwargs) -> HttpResponse:
        return self._dispatch(request)

    def delete(self, request: Request, **kwargs) -> HttpResponse:
        return self._dispatch(request)

    def _dispatch(self, request: Request) -> HttpResponse:
        workspace, workspace_error = _workspace_for_request(request)
        if workspace_error:
            return workspace_error

        path = request.path_info.removeprefix("/api/").strip("/")
        forwarded_content = _forwarded_request_body(request)

        # AppTension/PostgreSQL owns job lifecycle state. ClickHouse is used
        # below only for completed analytical run data.
        if request.method == "GET" and path == "backtests/jobs":
            try:
                limit = max(1, min(int(request.query_params.get("limit") or 20), 200))
            except (TypeError, ValueError):
                return Response({"detail": "limit must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
            jobs = WorkspaceBacktestReference.objects.filter(tenant=workspace)
            status_filter = request.query_params.get("status", "").strip()
            if status_filter:
                jobs = jobs.filter(status=status_filter)
            records = []
            for job in jobs[:limit]:
                progress = job.progress if isinstance(job.progress, dict) else {}
                records.append({
                    "job_id": job.job_id,
                    "run_id": job.run_id or job.job_id,
                    "ir_id": job.ir_id,
                    "status": job.status,
                    "start_date": job.configuration.get("start_date", ""),
                    "end_date": job.configuration.get("end_date", ""),
                    "submitted_at": job.created_at.isoformat() if job.created_at else None,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                    "progress": progress,
                    **progress,
                    "error_message": job.error_message,
                    "lean_output_path": progress.get("lean_output_path", ""),
                    "is_shared": False,
                })
            return Response({"jobs": records, "count": len(records)})

        direct_job_match = re.fullmatch(r"backtests/jobs/([^/]+)", path)
        if request.method == "GET" and direct_job_match:
            job = WorkspaceBacktestReference.objects.filter(
                tenant=workspace,
            ).filter(
                Q(job_id=direct_job_match.group(1)) | Q(run_id=direct_job_match.group(1))
            ).first()
            if job is None:
                return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
            progress = job.progress if isinstance(job.progress, dict) else {}
            return Response({
                "job_id": job.job_id,
                "run_id": job.run_id or job.job_id,
                "ir_id": job.ir_id,
                "status": job.status,
                **(job.configuration if isinstance(job.configuration, dict) else {}),
                **progress,
                "progress": progress,
                "error_message": job.error_message,
                "strategy_content_hash": job.strategy_content_hash,
                "is_shared": False,
            })

        if request.method == "GET" and (head_match := re.fullmatch(r"backtests/specs/([^/]+)/head", path)):
            reference = _accessible_strategy(workspace, request.user, head_match.group(1))
            if reference is None:
                return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
            record = _strategy_json(reference)
            return Response({
                "ir_id": reference.ir_id,
                "ir_content_hash": record["ir_content_hash"],
                "updated_at": record["updated_at"],
                "title": record["title"],
            })

        if request.method == "POST" and (ops_match := re.fullmatch(r"backtests/specs/([^/]+)/pipeline-ops", path)):
            reference = _accessible_strategy(workspace, request.user, ops_match.group(1))
            if reference is None:
                return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
            body = request.data if isinstance(request.data, dict) else {}
            ops = body.get("ops")
            if not isinstance(ops, list) or not ops:
                return Response({"detail": "ops must be a non-empty array"},
                                status=status.HTTP_400_BAD_REQUEST)
            current = _strategy_json(reference)["ir_content_hash"]
            expected_hash = str(body.get("expected_hash") or "").strip()
            if expected_hash and expected_hash != current:
                return Response({"detail": "expected_hash mismatch", "ir_content_hash": current,
                                 "code": "conflict"}, status=status.HTTP_409_CONFLICT)
            if not isinstance(reference.pipeline_document, dict):
                return Response({"detail": "spec has no authored pipeline_document",
                                 "code": "missing_pipeline"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                from screens.pipeline_ops import apply_pipeline_ops, compile_and_hash

                patched, changelog = apply_pipeline_ops(reference.pipeline_document, ops)
                compiled, _ = compile_and_hash(patched)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            raw = json.dumps(compiled, separators=(",", ":"), sort_keys=True)
            new_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            out = {
                "ir_id": reference.ir_id,
                "dry_run": bool(body.get("dry_run", True)),
                "pipeline_document": patched,
                "spec": compiled,
                "ir_content_hash": new_hash,
                "previous_hash": current,
                "changelog": changelog,
            }
            if out["dry_run"]:
                return Response(out)
            # Once a strategy has produced a run, preserve the exact version
            # used by that run. Pipeline edits create a lineage-linked fork.
            saved_reference = reference
            if WorkspaceBacktestReference.objects.filter(ir_id=reference.ir_id).exists():
                version = 2
                while WorkspaceStrategyReference.objects.filter(
                    ir_id=f"{reference.ir_id}-v{version}"
                ).exists():
                    version += 1
                saved_reference = WorkspaceStrategyReference.objects.create(
                    tenant=workspace,
                    created_by=request.user,
                    owner_user=request.user,
                    ir_id=f"{reference.ir_id}-v{version}",
                    title=reference.title,
                    notes=reference.notes,
                    category=reference.category,
                    tags=reference.tags,
                    spec_schema_version=reference.spec_schema_version,
                    compiler_version=reference.compiler_version,
                    parent_ir_id=reference.ir_id,
                    parent_content_hash=reference.content_hash,
                    mutation_type="fork",
                    changelog_notes=str(body.get("changelog_notes") or "Pipeline edit fork"),
                    is_template=False,
                    synced=True,
                )
            saved_reference.pipeline_document = patched
            saved_reference.spec = compiled
            saved_reference.content_hash = new_hash
            if saved_reference is reference:
                saved_reference.changelog_notes = str(body.get("changelog_notes") or reference.changelog_notes)
                saved_reference.mutation_type = "edit"
            saved_reference.save(update_fields=[
                "pipeline_document", "spec", "content_hash", "changelog_notes", "mutation_type", "updated_at",
            ])
            out["ir_id"] = saved_reference.ir_id
            out["saved"] = _strategy_json(saved_reference)
            return Response(out)

        backtest_reference = None
        deployment_reference = None
        deployment_reference_created = False
        broker_account_reference = None
        broker_account_created = False
        request_payload = None

        job_match = re.match(r"^backtests/jobs/([^/]+)(?:/(.*))?$", path)
        run_match = re.match(r"^backtests/runs/([^/]+)(?:/|$)", path)
        optimizer_match = re.match(r"^backtests/optimize/sessions/([^/]+)(?:/|$)", path)
        record_id = job_match.group(1) if job_match else run_match.group(1) if run_match else None
        record_reference = (
            WorkspaceBacktestReference.objects.filter(Q(job_id=record_id) | Q(run_id=record_id)).first()
            if record_id
            else None
        )
        if record_reference is not None and record_reference.tenant_id != workspace.id:
            return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)
        if record_id and record_reference is None:
            # Legacy ClickHouse rows without a PostgreSQL ownership record have
            # no trustworthy tenant mapping. Keep them quarantined until an
            # operator explicitly assigns them to a workspace.
            return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)
        optimizer_reference = (
            WorkspaceOptimizerReference.objects.filter(session_id=optimizer_match.group(1)).first()
            if optimizer_match
            else None
        )
        if optimizer_reference is not None and optimizer_reference.tenant_id != workspace.id:
            return Response({"detail": "Optimizer session not found."}, status=status.HTTP_404_NOT_FOUND)
        if optimizer_match and optimizer_reference is None:
            return Response({"detail": "Optimizer session not found."}, status=status.HTTP_404_NOT_FOUND)
        deployment_match = re.match(r"^live/deployments/([^/]+)(?:/|$)", path)
        deployment_reference = (
            WorkspaceDeploymentReference.objects.filter(deployment_id=deployment_match.group(1)).first()
            if deployment_match
            else None
        )
        if deployment_reference is not None and deployment_reference.tenant_id != workspace.id:
            return Response({"detail": "Deployment not found."}, status=status.HTTP_404_NOT_FOUND)
        if deployment_match and deployment_reference is None:
            return Response({"detail": "Deployment not found."}, status=status.HTTP_404_NOT_FOUND)
        broker_account_match = re.match(r"^live/accounts/([^/]+)(?:/(.*))?$", path)
        broker_profile_id = broker_account_match.group(1) if broker_account_match else None
        if broker_profile_id:
            broker_account_reference = WorkspaceBrokerAccountReference.objects.filter(
                profile_id=broker_profile_id
            ).first()
            if broker_account_reference is not None and broker_account_reference.tenant_id != workspace.id:
                return Response({"detail": "Broker account profile not found."}, status=status.HTTP_404_NOT_FOUND)
            if request.method in {"PATCH", "DELETE"} or (
                request.method == "POST" and bool(broker_account_match.group(2))
            ):
                if broker_account_reference is None:
                    return Response(
                        {
                            "detail": "Unowned local broker profiles are read-only. "
                            "Create a workspace profile to manage credentials."
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
        if request.method == "GET" and path == "backtests/compare":
            requested_run_ids = [
                item.strip() for item in request.query_params.get("run_ids", "").split(",") if item.strip()
            ]
            if any(
                not WorkspaceBacktestReference.objects.filter(
                    (Q(job_id=run_id) | Q(run_id=run_id)), tenant=workspace
                ).exists()
                for run_id in requested_run_ids
            ):
                return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.method == "GET" and path == "live/promotion-gate":
            ir_id = request.query_params.get("ir_id", "").strip()
            run_id = request.query_params.get("approval_backtest_run_id", "").strip()
            strategy_reference = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first() if ir_id else None
            run_reference = (
                WorkspaceBacktestReference.objects.filter(Q(job_id=run_id) | Q(run_id=run_id)).first()
                if run_id
                else None
            )
            if ir_id and strategy_reference is None:
                return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
            if strategy_reference is not None and (
                strategy_reference.tenant_id != workspace.id
                or (strategy_reference.owner_user_id != request.user.id and not strategy_reference.is_shared)
            ):
                return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
            if run_reference is not None and run_reference.tenant_id != workspace.id:
                return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)
            if run_id and run_reference is None:
                return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)

        # Backtest submission, optimizer launch, and paper deployment accept a
        # strategy ID in the request body instead of the URL. Keep those write
        # paths inside the same workspace boundary as spec edits.
        if request.method in {"POST", "PUT", "PATCH"}:
            if path in {
                "backtests/jobs",
                "backtests/optimize",
                "live/deployments",
                "live/accounts",
                "live/local-runtime",
            }:
                try:
                    request_payload = json.loads(request.body or b"{}")
                except (TypeError, ValueError):
                    request_payload = None
            body_strategy_key = {
                "backtests/jobs": "ir_id",
                "backtests/optimize": "base_ir_id",
                "live/deployments": "ir_id",
            }.get(path)
            if body_strategy_key and isinstance(request_payload, dict):
                ir_id = str(request_payload.get(body_strategy_key) or "").strip()
                if ir_id:
                    reference = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first()
                    if path == "live/deployments" and reference is not None and (
                        reference.tenant_id != workspace.id
                        or (reference.owner_user_id != request.user.id and not reference.is_shared)
                    ):
                        return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
                    if path == "live/deployments" and not _accessible_strategy(
                        workspace, request.user, ir_id
                    ):
                        return Response(
                            {"detail": "This action requires a saved strategy version in this workspace."},
                            status=status.HTTP_404_NOT_FOUND,
                        )
                    if reference is not None and (
                        not reference.synced
                        or reference.tenant_id != workspace.id
                        or (reference.owner_user_id != request.user.id and not reference.is_shared)
                    ):
                        return Response(
                            {"detail": "Strategy spec not found."},
                            status=status.HTTP_404_NOT_FOUND,
                        )

            if path == "live/deployments" and isinstance(request_payload, dict):
                approval_run_id = str(request_payload.get("approval_backtest_run_id") or "").strip()
                ir_id = str(request_payload.get("ir_id") or "").strip()
                strategy_reference = _accessible_strategy(workspace, request.user, ir_id) if ir_id else None
                if strategy_reference is None:
                    return Response(
                        {"detail": "Deployment requires a saved strategy version in this workspace."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                run_reference = (
                    WorkspaceBacktestReference.objects.filter(
                        Q(job_id=approval_run_id) | Q(run_id=approval_run_id)
                    ).first()
                    if approval_run_id
                    else None
                )
                if run_reference is not None and run_reference.tenant_id != workspace.id:
                    return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)
                if run_reference is not None and run_reference.strategy_content_hash != strategy_reference.content_hash:
                    return Response(
                        {"detail": "Approved backtest does not match the selected strategy version.",
                         "code": "strategy_hash_mismatch"},
                        status=status.HTTP_409_CONFLICT,
                    )

            if path == "live/local-runtime" and isinstance(request_payload, dict):
                action = str(request_payload.get("action") or "").strip()
                if action != "stop":
                    return Response(
                        {"detail": "Remote deployment starts and liquidation are disabled during migration."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                deployment_id = str(request_payload.get("deployment_id") or "").strip()
                deployment_reference = WorkspaceDeploymentReference.objects.filter(
                    deployment_id=deployment_id
                ).first()
                if deployment_reference is None or deployment_reference.tenant_id != workspace.id:
                    return Response({"detail": "Deployment not found."}, status=status.HTTP_404_NOT_FOUND)

            if path == "live/accounts" and isinstance(request_payload, dict):
                environment = str(request_payload.get("environment") or "paper").strip().lower()
                if environment != "paper":
                    return Response(
                        {"detail": "AppTension can manage paper brokerage profiles only."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                profile_id = str(request_payload.get("id") or "").strip()
                if profile_id:
                    broker_account_reference = WorkspaceBrokerAccountReference.objects.filter(
                        profile_id=profile_id
                    ).first()
                    if broker_account_reference is None or broker_account_reference.tenant_id != workspace.id:
                        return Response(
                            {
                                "detail": "Unowned local broker profiles are read-only. "
                                "Create a workspace profile to manage credentials."
                            },
                            status=status.HTTP_403_FORBIDDEN,
                        )
                else:
                    profile_id = str(uuid.uuid4())
                    request_payload["id"] = profile_id
                    try:
                        broker_account_reference = WorkspaceBrokerAccountReference.objects.create(
                            tenant=workspace,
                            created_by=request.user,
                            profile_id=profile_id,
                        )
                    except IntegrityError:
                        return Response(
                            {"detail": "This broker account profile ID is already registered."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    broker_account_created = True
                    forwarded_content = json.dumps(request_payload, separators=(",", ":")).encode("utf-8")

            if path == "backtests/jobs" and isinstance(request_payload, dict):
                ir_id = str(request_payload.get("ir_id") or "").strip()
                if ir_id:
                    strategy = _accessible_strategy(workspace, request.user, ir_id)
                    if strategy is None:
                        return Response({"detail": "Strategy spec not found in this workspace."},
                                        status=status.HTTP_404_NOT_FOUND)
                    job_id = str(request_payload.get("job_id") or "").strip() or str(uuid.uuid4())
                    request_payload["job_id"] = job_id
                    algorithm_json = json.dumps(strategy.spec, separators=(",", ":"), sort_keys=True)
                    strategy_hash = strategy.content_hash or hashlib.sha256(
                        algorithm_json.encode("utf-8")
                    ).hexdigest()
                    extra_env = request_payload.get("extra_env")
                    if extra_env is None:
                        extra_env = {}
                    if not isinstance(extra_env, dict):
                        return Response({"detail": "extra_env must be an object"},
                                        status=status.HTTP_400_BAD_REQUEST)
                    # The LEAN worker receives the immutable version selected at
                    # queue time. It does not resolve an editable spec from CH.
                    extra_env = dict(extra_env)
                    extra_env["SIGMARAIL_STRATEGY_BASE64"] = base64.b64encode(
                        algorithm_json.encode("utf-8")
                    ).decode("ascii")
                    extra_env["SIGMARAIL_STRATEGY_CONTENT_HASH"] = strategy_hash
                    extra_env["SIGMARAIL_STRATEGY_SCHEMA_VERSION"] = str(strategy.spec_schema_version or 1)
                    request_payload["extra_env"] = extra_env
                    try:
                        backtest_reference = WorkspaceBacktestReference.objects.create(
                            tenant=workspace,
                            created_by=request.user,
                            ir_id=ir_id,
                            job_id=job_id,
                            # SigmaRail's runner uses the job ID as its strategy_runs run ID.
                            run_id=job_id,
                            strategy_content_hash=strategy_hash,
                            strategy_snapshot=strategy.spec,
                            configuration={
                                key: value for key, value in request_payload.items()
                                if key not in {"extra_env", "job_id", "ir_id"}
                            }
                            | {
                                "strategy_title": strategy.title,
                                "strategy_schema_version": strategy.spec_schema_version or 1,
                            },
                        )
                    except IntegrityError:
                        return Response(
                            {"detail": "This backtest job ID is already registered."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    forwarded_content = json.dumps(request_payload, separators=(",", ":")).encode("utf-8")

            if path == "live/deployments" and isinstance(request_payload, dict):
                ir_id = str(request_payload.get("ir_id") or "").strip()
                deployment_id = str(request_payload.get("deployment_id") or "").strip() or str(uuid.uuid4())
                if ir_id:
                    strategy_reference = _accessible_strategy(workspace, request.user, ir_id)
                    if strategy_reference is None:
                        return Response(
                            {"detail": "Deployment requires a saved strategy version in this workspace."},
                            status=status.HTTP_404_NOT_FOUND,
                        )
                    request_payload["deployment_id"] = deployment_id
                    try:
                        deployment_reference = WorkspaceDeploymentReference.objects.create(
                            tenant=workspace,
                            created_by=request.user,
                            ir_id=ir_id,
                            deployment_id=deployment_id,
                            strategy_content_hash=strategy_reference.content_hash,
                            approval_run_id=str(request_payload.get("approval_backtest_run_id") or "").strip(),
                            configuration={
                                key: value for key, value in request_payload.items()
                                if key not in {"deployment_id", "ir_id"}
                            },
                        )
                        deployment_reference_created = True
                    except IntegrityError:
                        return Response(
                            {"detail": "This deployment ID is already registered."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    forwarded_content = json.dumps(request_payload, separators=(",", ":")).encode("utf-8")

        strategy_match = re.match(r"^/api/backtests/specs/([^/]+)(?:/|$)", request.path_info)
        if strategy_match:
            ir_id = strategy_match.group(1)
            reference = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first()
            if reference is not None:
                if not reference.synced:
                    return Response(
                        {"detail": "Strategy spec not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if reference.tenant_id != workspace.id:
                    return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
                if reference.owner_user_id != request.user.id and not reference.is_shared:
                    return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
                if reference.is_shared and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                    return Response(
                        {
                            "detail": "Shared strategies are read-only. Fork the strategy before saving changes.",
                            "code": "strategy_shared_read_only",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                return Response(
                    {
                        "detail": "Strategy spec not found in this workspace.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        headers = {name: value for name in self.request_headers if (value := request.headers.get(name)) is not None}
        try:
            upstream = dispatch_api_request(
                request.method,
                request.get_full_path().split("?", 1)[0],
                query=request.META.get("QUERY_STRING", ""),
                content=forwarded_content,
                user=request.user,
                session=getattr(request._request, "session", None),
                headers=headers,
            )
        except InProcessDispatchError:
            if broker_account_created and broker_account_reference is not None:
                broker_account_reference.delete()
            return JsonResponse({"detail": "The SigmaRail API handler is unavailable in AppTension."}, status=503)

        if backtest_reference is not None and upstream.status_code >= 400:
            backtest_reference.delete()
        if deployment_reference_created and deployment_reference is not None and upstream.status_code >= 400:
            deployment_reference.delete()
        if broker_account_reference is not None and request.method == "POST" and upstream.status_code >= 400:
            if broker_account_created:
                broker_account_reference.delete()

        response = HttpResponse(content=upstream.content, status=upstream.status_code)
        for header in self.response_headers:
            if value := upstream.headers.get(header):
                response[header] = value

        try:
            response_payload = upstream.json()
        except ValueError:
            response_payload = None
        if upstream.status_code >= 400 and response_payload is None and upstream.content:
            # Product APIs return JSON. Do not forward framework debug pages or
            # other HTML error bodies into the browser, where they become a
            # noisy "Invalid JSON" message and may disclose internal details.
            return JsonResponse(
                {
                    "detail": "SigmaRail API returned a non-JSON error response.",
                    "code": "upstream_non_json",
                    "upstream_status": upstream.status_code,
                },
                status=upstream.status_code,
            )
        if not isinstance(response_payload, dict):
            return response

        if path == "live/accounts" and request.method == "GET":
            accounts = {
                item.profile_id: item
                for item in WorkspaceBrokerAccountReference.objects.filter(tenant=workspace)
            }
            profiles = response_payload.get("profiles")
            if isinstance(profiles, list):
                visible_profiles = []
                for profile in profiles:
                    if not isinstance(profile, dict):
                        continue
                    reference = accounts.get(str(profile.get("id") or ""))
                    if reference is None:
                        continue
                    if not reference.provider:
                        _save_broker_account_metadata(reference, profile, overwrite=True)
                    visible_profiles.append(_serialize_workspace_broker_account(profile, reference))
                response_payload["profiles"] = visible_profiles
                response_payload["count"] = len(visible_profiles)

        if path == "live/brokerages" and request.method == "GET":
            brokerages = response_payload.get("brokerages")
            if isinstance(brokerages, list):
                paper_brokerages = []
                for item in brokerages:
                    if not isinstance(item, dict):
                        continue
                    environments = item.get("environments")
                    if not isinstance(environments, dict) or "paper" not in environments:
                        continue
                    paper_brokerages.append({**item, "environments": {"paper": environments["paper"]}})
                response_payload["brokerages"] = paper_brokerages

        if path == "live/accounts" and request.method == "POST" and upstream.status_code < 400:
            actual_id = str(response_payload.get("id") or "").strip()
            if broker_account_reference is None or actual_id != broker_account_reference.profile_id:
                if broker_account_created and broker_account_reference is not None:
                    broker_account_reference.delete()
                return JsonResponse({"detail": "SigmaRail API returned an invalid broker profile ID."}, status=502)
            account_metadata = dict(request_payload or {})
            account_metadata.update(response_payload)
            _save_broker_account_metadata(broker_account_reference, account_metadata, overwrite=True)

        if broker_account_match and request.method == "PATCH" and upstream.status_code < 400:
            if broker_account_reference is not None and isinstance(request.data, dict):
                _save_broker_account_metadata(broker_account_reference, request.data, overwrite=True)

        if broker_account_match and request.method == "DELETE" and upstream.status_code < 400:
            if broker_account_reference is not None:
                broker_account_reference.delete()

        if backtest_reference is not None and isinstance(response_payload, dict):
            actual_job_id = str(response_payload.get("job_id") or backtest_reference.job_id).strip()
            if actual_job_id != backtest_reference.job_id:
                backtest_reference.job_id = actual_job_id
                backtest_reference.run_id = actual_job_id
                backtest_reference.save(update_fields=["job_id", "run_id", "updated_at"])
            response_payload["is_shared"] = False

        if deployment_reference is not None and path == "live/local-runtime" and isinstance(response_payload, dict):
            deployment = response_payload.get("deployment")
            actual_deployment_id = str(
                deployment.get("deployment_id") or deployment_reference.deployment_id
            ).strip() if isinstance(deployment, dict) else deployment_reference.deployment_id
            if actual_deployment_id != deployment_reference.deployment_id:
                deployment_reference.deployment_id = actual_deployment_id
                deployment_reference.save(update_fields=["deployment_id", "updated_at"])
            if isinstance(deployment, dict):
                deployment_reference.status = str(deployment.get("status") or deployment_reference.status)[:24]
                if deployment_reference.status in {"stopped", "failed", "cancelled"}:
                    deployment_reference.stopped_at = timezone.now()
                deployment_reference.save(update_fields=["deployment_id", "status", "stopped_at", "updated_at"])
                deployment["is_shared"] = False

        if deployment_reference is not None and path != "live/local-runtime" and isinstance(response_payload, dict):
            actual_deployment_id = str(
                response_payload.get("deployment_id") or deployment_reference.deployment_id
            ).strip()
            if actual_deployment_id != deployment_reference.deployment_id:
                deployment_reference.deployment_id = actual_deployment_id
            response_status = str(response_payload.get("status") or deployment_reference.status)[:24]
            deployment_reference.status = response_status
            deployment_reference.save(update_fields=["deployment_id", "status", "updated_at"])
            response_payload["is_shared"] = False

        if path == "backtests/optimize" and request.method == "POST" and upstream.status_code < 400:
            session_id = str(response_payload.get("session_id") or "").strip()
            base_ir_id = str(response_payload.get("base_ir_id") or "").strip()
            if session_id and base_ir_id:
                base_strategy = WorkspaceStrategyReference.objects.filter(
                    tenant=workspace, ir_id=base_ir_id
                ).first()
                optimizer_reference, _ = WorkspaceOptimizerReference.objects.get_or_create(
                    session_id=session_id,
                    defaults={
                        "tenant": workspace,
                        "created_by": request.user,
                        "base_ir_id": base_ir_id,
                        "base_strategy_content_hash": base_strategy.content_hash if base_strategy else "",
                        "configuration": request_payload if isinstance(request_payload, dict) else {},
                        "status": str(response_payload.get("status") or "running")[:24],
                    },
                )
                response_payload["is_shared"] = optimizer_reference.tenant_id != workspace.id
            optimizer_jobs = response_payload.get("jobs") if isinstance(response_payload, dict) else None
            if isinstance(optimizer_jobs, list):
                for job in optimizer_jobs:
                    if not isinstance(job, dict):
                        continue
                    job_id = str(job.get("job_id") or "").strip()
                    ir_id = str(job.get("ir_id") or "").strip()
                    if not job_id or not ir_id:
                        continue
                    strategy_reference, _ = WorkspaceStrategyReference.objects.get_or_create(
                        ir_id=ir_id,
                        defaults={
                            "tenant": workspace,
                            "is_shared": True,
                            "synced": True,
                        },
                    )
                    job_reference, _ = WorkspaceBacktestReference.objects.get_or_create(
                        job_id=job_id,
                        defaults={
                            "tenant": workspace,
                            "created_by": request.user,
                            "ir_id": ir_id,
                            "run_id": job_id,
                        },
                    )
                    job["is_shared"] = (
                        strategy_reference.tenant_id != workspace.id or job_reference.tenant_id != workspace.id
                    )

        if record_reference is not None and isinstance(response_payload, dict):
            response_payload["is_shared"] = False

        if optimizer_reference is not None and isinstance(response_payload, dict):
            response_payload["is_shared"] = False
        if deployment_match and isinstance(response_payload, dict):
            response_payload["is_shared"] = False

        if request.method == "GET" and path in {"backtests/jobs", "backtests/runs"}:
            list_key = "jobs" if path == "backtests/jobs" else "runs"
            records = response_payload.get(list_key)
            if isinstance(records, list):
                identifiers = [
                    str((record or {}).get("job_id") or (record or {}).get("run_id") or "")
                    for record in records
                    if isinstance(record, dict)
                ]
                owner_refs = WorkspaceBacktestReference.objects.filter(
                    Q(job_id__in=identifiers) | Q(run_id__in=identifiers)
                )
                owners = {}
                for ref in owner_refs:
                    owners[ref.job_id] = ref
                    if ref.run_id:
                        owners[ref.run_id] = ref
                visible = []
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    item = dict(record)
                    identifier = str(item.get("job_id") or item.get("run_id") or "")
                    owner = owners.get(identifier)
                    if owner is None or owner.tenant_id != workspace.id:
                        continue
                    item["is_shared"] = False
                    visible.append(item)
                response_payload[list_key] = visible
                response_payload["count"] = len(visible)
                response = HttpResponse(
                    content=json.dumps(response_payload, default=str).encode("utf-8"),
                    status=upstream.status_code,
                    content_type="application/json",
                )

        if request.method == "GET" and path == "backtests/optimize/sessions":
            sessions = response_payload.get("sessions")
            if isinstance(sessions, list):
                session_ids = [str(item.get("session_id") or "") for item in sessions if isinstance(item, dict)]
                owners = {
                    item.session_id: item
                    for item in WorkspaceOptimizerReference.objects.filter(session_id__in=session_ids)
                }
                visible_sessions = []
                for session in sessions:
                    if not isinstance(session, dict):
                        continue
                    item = dict(session)
                    owner = owners.get(str(item.get("session_id") or ""))
                    if owner is None or owner.tenant_id != workspace.id:
                        continue
                    item["is_shared"] = False
                    visible_sessions.append(item)
                response_payload["sessions"] = visible_sessions
                response_payload["count"] = len(visible_sessions)

        if request.method == "GET" and path == "live/deployments":
            deployments = response_payload.get("deployments")
            if isinstance(deployments, list):
                deployment_ids = [
                    str(item.get("deployment_id") or "") for item in deployments if isinstance(item, dict)
                ]
                owners = {
                    item.deployment_id: item
                    for item in WorkspaceDeploymentReference.objects.filter(deployment_id__in=deployment_ids)
                }
                visible_deployments = []
                for deployment in deployments:
                    if not isinstance(deployment, dict):
                        continue
                    item = dict(deployment)
                    owner = owners.get(str(item.get("deployment_id") or ""))
                    if owner is None or owner.tenant_id != workspace.id:
                        continue
                    item["is_shared"] = False
                    visible_deployments.append(item)
                response_payload["deployments"] = visible_deployments
                response_payload["count"] = len(visible_deployments)

        if request.method == "GET" and path == "live/local-runtime":
            response_payload["remote_start_supported"] = False
            response_payload["remote_stop_supported"] = bool(response_payload.get("enabled"))
            response_payload["remote_liquidation_supported"] = False
            owned_ids = set(
                WorkspaceDeploymentReference.objects.filter(tenant=workspace).values_list("deployment_id", flat=True)
            )
            deployments = response_payload.get("deployments")
            if isinstance(deployments, list):
                visible = [
                    item
                    for item in deployments
                    if isinstance(item, dict)
                    and item.get("mode") == "paper"
                    and str(item.get("deployment_id") or "") in owned_ids
                ]
                response_payload["deployments"] = visible
                response_payload["active_count"] = sum(
                    1 for item in visible if item.get("status") in {"starting", "stopping", "running"}
                )
                response_payload["status"] = visible[0].get("status", "idle") if visible else "idle"
                deployment = response_payload.get("deployment")
                selected_id = str(deployment.get("deployment_id") or "") if isinstance(deployment, dict) else ""
                response_payload["deployment"] = next(
                    (item for item in visible if str(item.get("deployment_id") or "") == selected_id),
                    visible[0] if visible else None,
                )

        response = HttpResponse(
            content=json.dumps(response_payload, default=str).encode("utf-8"),
            status=upstream.status_code,
            content_type="application/json",
        )
        for header in self.response_headers:
            if value := upstream.headers.get(header):
                response[header] = value

        return response
