"""Authenticated storage for user-owned five-slot framework templates."""

from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WorkspaceStrategyFrameworkTemplate
from .views import _workspace_for_request


def _serialize(template: WorkspaceStrategyFrameworkTemplate) -> dict:
    return template.to_dict()


def _template_for_owner(template_id: str, *, workspace, user):
    queryset = WorkspaceStrategyFrameworkTemplate.objects.filter(tenant=workspace, owner_user=user)
    try:
        parsed_id = UUID(template_id)
    except (TypeError, ValueError, AttributeError):
        parsed_id = None
    template = queryset.filter(pk=parsed_id).first() if parsed_id else None
    if template is None:
        template = queryset.filter(name__iexact=template_id).first()
    return template


def _template_by_id(template_id: str, *, workspace, user):
    try:
        parsed_id = UUID(template_id)
    except (TypeError, ValueError, AttributeError):
        return None
    return WorkspaceStrategyFrameworkTemplate.objects.filter(
        pk=parsed_id,
        tenant=workspace,
        owner_user=user,
    ).first()


class WorkspaceStrategyFrameworkTemplatesView(APIView):
    """List and save framework templates owned by the active user."""

    def get(self, request: Request) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        templates = WorkspaceStrategyFrameworkTemplate.objects.filter(
            tenant=workspace,
            owner_user=request.user,
        )
        rows = [_serialize(template) for template in templates]
        return Response({"templates": rows, "count": len(rows)})

    def post(self, request: Request) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        name = str(body.get("name") or "").strip()
        description = str(body.get("description") or "").strip()
        category = str(body.get("category") or "Custom").strip() or "Custom"
        framework = body.get("framework")
        if not name:
            return Response({"detail": "name is required"}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 128:
            return Response({"detail": "name must be at most 128 characters"}, status=status.HTTP_400_BAD_REQUEST)
        if len(category) > 64:
            return Response({"detail": "category must be at most 64 characters"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(framework, dict):
            return Response({"detail": "framework must be a valid dictionary"}, status=status.HTTP_400_BAD_REQUEST)
        if WorkspaceStrategyFrameworkTemplate.objects.filter(
            tenant=workspace,
            owner_user=request.user,
            name__iexact=name,
        ).exists():
            return Response(
                {"detail": f"Template with name '{name}' already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                template = WorkspaceStrategyFrameworkTemplate.objects.create(
                    tenant=workspace,
                    created_by=request.user,
                    owner_user=request.user,
                    name=name,
                    description=description,
                    category=category,
                    framework=framework,
                )
        except IntegrityError:
            return Response(
                {"detail": f"Template with name '{name}' already exists"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize(template), status=status.HTTP_201_CREATED)


class WorkspaceStrategyFrameworkTemplateDetailView(APIView):
    """Read, edit, or delete a framework template owned by the active user."""

    def get(self, request: Request, template_id: str) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        template = _template_for_owner(template_id, workspace=workspace, user=request.user)
        if template is None:
            return Response({"detail": "template not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_serialize(template))

    def put(self, request: Request, template_id: str) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        template = _template_by_id(template_id, workspace=workspace, user=request.user)
        if template is None:
            return Response({"detail": "template not found"}, status=status.HTTP_404_NOT_FOUND)

        body = request.data if isinstance(request.data, dict) else {}
        if "name" in body:
            name = str(body["name"] or "").strip()
            if not name:
                return Response({"detail": "name cannot be empty"}, status=status.HTTP_400_BAD_REQUEST)
            if len(name) > 128:
                return Response({"detail": "name must be at most 128 characters"}, status=status.HTTP_400_BAD_REQUEST)
            if (
                WorkspaceStrategyFrameworkTemplate.objects.filter(
                    tenant=workspace,
                    owner_user=request.user,
                    name__iexact=name,
                )
                .exclude(pk=template.pk)
                .exists()
            ):
                return Response(
                    {"detail": f"Template with name '{name}' already exists"},
                    status=status.HTTP_409_CONFLICT,
                )
            template.name = name
        if "description" in body:
            template.description = str(body["description"] or "").strip()
        if "category" in body:
            category = str(body["category"] or "").strip() or "Custom"
            if len(category) > 64:
                return Response(
                    {"detail": "category must be at most 64 characters"}, status=status.HTTP_400_BAD_REQUEST
                )
            template.category = category
        if "framework" in body:
            if not isinstance(body["framework"], dict):
                return Response({"detail": "framework must be a dictionary"}, status=status.HTTP_400_BAD_REQUEST)
            template.framework = body["framework"]

        try:
            with transaction.atomic():
                template.save()
        except IntegrityError:
            return Response(
                {"detail": f"Template with name '{template.name}' already exists"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize(template))

    def delete(self, request: Request, template_id: str) -> Response:
        workspace, error = _workspace_for_request(request)
        if error:
            return error
        template = _template_by_id(template_id, workspace=workspace, user=request.user)
        if template is None:
            return Response({"detail": "template not found"}, status=status.HTTP_404_NOT_FOUND)
        template.delete()
        return Response({"deleted": True, "id": template_id})
