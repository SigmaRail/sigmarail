import uuid

from django.conf import settings
from django.db import models

from common.models import TenantDependentModelMixin, TimestampedMixin


class WorkspaceScreen(TenantDependentModelMixin, TimestampedMixin):
    """A user-owned universe screen, authorized within its application workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    spec = models.JSONField()
    source_template_id = models.CharField(max_length=160, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sigmarail_screens",
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_sigmarail_screens",
    )
    is_shared = models.BooleanField(default=False)

    class Meta:
        ordering = ["name", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "owner_user", "name"],
                name="sigmarail_screen_unique_name_per_owner",
            ),
        ]

    def __str__(self):
        return self.name


class WorkspaceStrategyReference(TenantDependentModelMixin, TimestampedMixin):
    """User ownership for a strategy spec persisted by SigmaRail Core."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ir_id = models.CharField(max_length=255, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sigmarail_strategies",
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_sigmarail_strategies",
    )
    is_shared = models.BooleanField(default=False)
    synced = models.BooleanField(default=False)

    class Meta:
        ordering = ["ir_id"]

    def __str__(self):
        return self.ir_id


class WorkspaceStrategyFrameworkTemplate(TenantDependentModelMixin, TimestampedMixin):
    """A private, tenant-scoped framework template saved by one user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=64, default="Custom")
    framework = models.JSONField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sigmarail_framework_templates",
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_sigmarail_framework_templates",
    )

    class Meta:
        ordering = ["-updated_at", "name"]
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("name"),
                models.F("tenant"),
                models.F("owner_user"),
                name="sigmarail_template_unique_name_per_owner",
            ),
        ]

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "is_system": False,
            "framework": self.framework,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __str__(self):
        return self.name


class WorkspaceBacktestReference(TenantDependentModelMixin, TimestampedMixin):
    """Organization ownership for a queued backtest and its result run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_id = models.CharField(max_length=255, unique=True)
    run_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    ir_id = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sigmarail_backtests",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.job_id


class WorkspaceOptimizerReference(TenantDependentModelMixin, TimestampedMixin):
    """Organization ownership for an optimizer session persisted by SigmaRail Core."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.CharField(max_length=255, unique=True)
    base_ir_id = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sigmarail_optimizer_sessions",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.session_id


class WorkspaceDeploymentReference(TenantDependentModelMixin, TimestampedMixin):
    """Organization ownership for a paper deployment registered by Studio."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deployment_id = models.CharField(max_length=255, unique=True)
    ir_id = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sigmarail_deployments",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.deployment_id


class WorkspaceBrokerAccountReference(TenantDependentModelMixin, TimestampedMixin):
    """Workspace-owned, non-secret broker profile configuration."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_id = models.CharField(max_length=255, unique=True)
    provider = models.CharField(max_length=32, blank=True, default="")
    data_provider = models.CharField(max_length=32, blank=True, default="")
    environment = models.CharField(max_length=16, default="paper")
    display_name = models.CharField(max_length=80, blank=True, default="")
    account_identifier = models.CharField(max_length=128, blank=True, default="")
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_sigmarail_broker_accounts",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.display_name or self.profile_id
