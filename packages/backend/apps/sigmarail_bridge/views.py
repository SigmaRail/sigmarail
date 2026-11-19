from __future__ import annotations

import json
import re
import uuid

from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.http import HttpResponse
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


class WorkspaceStrategySpecsView(APIView):
    """Keep strategy payloads in SigmaRail Core and user ownership in PostgreSQL."""

    def get(self, request: Request) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        try:
            upstream = _dispatch_domain_api(
                "GET",
                "/api/backtests/specs",
                query=request.META.get("QUERY_STRING", ""),
                request=request,
            )
            payload = upstream.json()
        except (InProcessDispatchError, ValueError):
            return Response({"detail": "Strategy catalog is unavailable."}, status=status.HTTP_502_BAD_GATEWAY)
        if upstream.status_code >= 400:
            return _domain_json_response(upstream)
        if not isinstance(payload, dict) or not isinstance(payload.get("specs"), list):
            return Response(
                {"detail": "SigmaRail API returned an invalid strategy catalog."}, status=status.HTTP_502_BAD_GATEWAY
            )

        ir_ids = [str(item.get("ir_id", "")) for item in payload["specs"] if isinstance(item, dict)]
        owners = {ref.ir_id: ref for ref in WorkspaceStrategyReference.objects.filter(ir_id__in=ir_ids)}
        visible = []
        for record in payload["specs"]:
            if not isinstance(record, dict):
                continue
            item = dict(record)
            reference = owners.get(str(item.get("ir_id", "")))
            if reference is not None:
                if not reference.synced:
                    continue
                if reference.tenant_id != workspace.id:
                    continue
                if reference.owner_user_id != request.user.id and not reference.is_shared:
                    continue
                item["is_shared"] = reference.is_shared
            else:
                item["is_shared"] = not bool(item.get("is_system"))
            visible.append(item)
        payload["specs"] = visible
        payload["count"] = len(visible)
        return Response(payload, status=upstream.status_code)

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
        if reference is None:
            try:
                existing = _dispatch_domain_api("GET", f"/api/backtests/specs/{ir_id}", request=request)
            except InProcessDispatchError:
                return Response({"detail": "Could not verify the strategy ID."}, status=status.HTTP_502_BAD_GATEWAY)
            if existing.status_code != status.HTTP_404_NOT_FOUND:
                if existing.status_code >= 400:
                    return _domain_json_response(existing)
                return Response(
                    {
                        "detail": "Existing shared strategies are read-only. Fork the strategy to save a user-owned copy.",
                        "code": "strategy_shared_read_only",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                reference = WorkspaceStrategyReference.objects.create(
                    tenant=workspace,
                    created_by=request.user,
                    owner_user=request.user,
                    ir_id=ir_id,
                )
            except IntegrityError:
                return Response(
                    {"detail": "This strategy ID is already owned by another workspace."},
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            upstream = _dispatch_domain_api(
                "POST",
                "/api/backtests/specs",
                content=json.dumps(body, separators=(",", ":")).encode("utf-8"),
                request=request,
            )
        except InProcessDispatchError:
            if reference is not None and not reference.synced:
                reference.delete()
            return Response({"detail": "Strategy save service is unavailable."}, status=status.HTTP_502_BAD_GATEWAY)

        result = _domain_json_response(upstream)
        if result.status_code >= 400:
            if reference is not None and not reference.synced:
                reference.delete()
            return result
        reference.synced = True
        reference.save(update_fields=["synced", "updated_at"])
        if isinstance(result.data, dict):
            result.data["is_shared"] = False
        return result


class WorkspaceStrategySpecDetailView(APIView):
    """Read a shared legacy strategy or a user-owned strategy spec."""

    def get(self, request: Request, ir_id: str) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        reference = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first()
        if reference is not None:
            if (
                not reference.synced
                or reference.tenant_id != workspace.id
                or (reference.owner_user_id != request.user.id and not reference.is_shared)
            ):
                return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            upstream = _dispatch_domain_api("GET", f"/api/backtests/specs/{ir_id}", request=request)
        except InProcessDispatchError:
            return Response({"detail": "Strategy service is unavailable."}, status=status.HTTP_502_BAD_GATEWAY)
        result = _domain_json_response(upstream)
        if upstream.status_code == status.HTTP_200_OK and isinstance(result.data, dict):
            result.data["is_shared"] = (
                reference.is_shared if reference is not None else not bool(result.data.get("is_system"))
            )
        return result


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
        forwarded_content = request.body or None
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
        record_reference = WorkspaceBacktestReference.objects.filter(job_id=record_id).first() if record_id else None
        if record_reference is not None and record_reference.tenant_id != workspace.id:
            return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)
        if job_match and job_match.group(2) == "cancel" and request.method == "POST" and record_reference is None:
            return Response(
                {
                    "detail": "Shared legacy backtests are read-only and cannot be cancelled.",
                    "code": "shared_backtest_read_only",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        optimizer_reference = (
            WorkspaceOptimizerReference.objects.filter(session_id=optimizer_match.group(1)).first()
            if optimizer_match
            else None
        )
        if optimizer_reference is not None and optimizer_reference.tenant_id != workspace.id:
            return Response({"detail": "Optimizer session not found."}, status=status.HTTP_404_NOT_FOUND)
        deployment_match = re.match(r"^live/deployments/([^/]+)(?:/|$)", path)
        deployment_reference = (
            WorkspaceDeploymentReference.objects.filter(deployment_id=deployment_match.group(1)).first()
            if deployment_match
            else None
        )
        if deployment_reference is not None and deployment_reference.tenant_id != workspace.id:
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
                WorkspaceBacktestReference.objects.filter(job_id=run_id).exclude(tenant_id=workspace.id).exists()
                for run_id in requested_run_ids
            ):
                return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.method == "GET" and path == "live/promotion-gate":
            ir_id = request.query_params.get("ir_id", "").strip()
            run_id = request.query_params.get("approval_backtest_run_id", "").strip()
            strategy_reference = WorkspaceStrategyReference.objects.filter(ir_id=ir_id).first() if ir_id else None
            run_reference = WorkspaceBacktestReference.objects.filter(job_id=run_id).first() if run_id else None
            if strategy_reference is not None and (
                strategy_reference.tenant_id != workspace.id
                or (strategy_reference.owner_user_id != request.user.id and not strategy_reference.is_shared)
            ):
                return Response({"detail": "Strategy spec not found."}, status=status.HTTP_404_NOT_FOUND)
            if run_reference is not None and run_reference.tenant_id != workspace.id:
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
                run_reference = (
                    WorkspaceBacktestReference.objects.filter(job_id=approval_run_id).first()
                    if approval_run_id
                    else None
                )
                if run_reference is not None and run_reference.tenant_id != workspace.id:
                    return Response({"detail": "Backtest record not found."}, status=status.HTTP_404_NOT_FOUND)

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
                    job_id = str(request_payload.get("job_id") or "").strip() or str(uuid.uuid4())
                    request_payload["job_id"] = job_id
                    try:
                        backtest_reference = WorkspaceBacktestReference.objects.create(
                            tenant=workspace,
                            created_by=request.user,
                            ir_id=ir_id,
                            job_id=job_id,
                            # SigmaRail's runner uses the job ID as its strategy_runs run ID.
                            run_id=job_id,
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
                    request_payload["deployment_id"] = deployment_id
                    try:
                        deployment_reference = WorkspaceDeploymentReference.objects.create(
                            tenant=workspace,
                            created_by=request.user,
                            ir_id=ir_id,
                            deployment_id=deployment_id,
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
            elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                return Response(
                    {
                        "detail": "Shared legacy strategies are read-only. Fork the strategy before saving changes.",
                        "code": "strategy_shared_read_only",
                    },
                    status=status.HTTP_403_FORBIDDEN,
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
                deployment["is_shared"] = False

        if deployment_reference is not None and path != "live/local-runtime" and isinstance(response_payload, dict):
            actual_deployment_id = str(
                response_payload.get("deployment_id") or deployment_reference.deployment_id
            ).strip()
            if actual_deployment_id != deployment_reference.deployment_id:
                deployment_reference.deployment_id = actual_deployment_id
                deployment_reference.save(update_fields=["deployment_id", "updated_at"])
            response_payload["is_shared"] = False

        if path == "backtests/optimize" and request.method == "POST" and upstream.status_code < 400:
            session_id = str(response_payload.get("session_id") or "").strip()
            base_ir_id = str(response_payload.get("base_ir_id") or "").strip()
            if session_id and base_ir_id:
                optimizer_reference, _ = WorkspaceOptimizerReference.objects.get_or_create(
                    session_id=session_id,
                    defaults={
                        "tenant": workspace,
                        "created_by": request.user,
                        "base_ir_id": base_ir_id,
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

        if record_id and record_reference is None and isinstance(response_payload, dict):
            response_payload["is_shared"] = True
        if optimizer_reference is not None and isinstance(response_payload, dict):
            response_payload["is_shared"] = False
        if optimizer_match and optimizer_reference is None and isinstance(response_payload, dict):
            response_payload["is_shared"] = True
        if deployment_match and isinstance(response_payload, dict):
            response_payload["is_shared"] = deployment_reference is None

        if request.method == "GET" and path in {"backtests/jobs", "backtests/runs"}:
            list_key = "jobs" if path == "backtests/jobs" else "runs"
            records = response_payload.get(list_key)
            if isinstance(records, list):
                identifiers = [
                    str((record or {}).get("job_id") or (record or {}).get("run_id") or "")
                    for record in records
                    if isinstance(record, dict)
                ]
                owners = {ref.job_id: ref for ref in WorkspaceBacktestReference.objects.filter(job_id__in=identifiers)}
                visible = []
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    item = dict(record)
                    identifier = str(item.get("job_id") or item.get("run_id") or "")
                    owner = owners.get(identifier)
                    if owner is not None and owner.tenant_id != workspace.id:
                        continue
                    item["is_shared"] = owner is None
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
                    if owner is not None and owner.tenant_id != workspace.id:
                        continue
                    item["is_shared"] = owner is None
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
                    if owner is not None and owner.tenant_id != workspace.id:
                        continue
                    item["is_shared"] = owner is None
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
