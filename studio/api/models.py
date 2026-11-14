from django.db import models
import uuid


class SavedScreen(models.Model):
    """User-saved universe_query_v1 screens — SQLite backend for ScreenRepository.

    Prefer ClickHouse ``strategy_screens`` via ``SCREEN_STORE=ch`` in production
    (see ``screens/screen_store.py``, contract C-SCREEN-PERSISTENCE).
    """

    name = models.CharField(max_length=128, unique=True)
    spec = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def to_dict(self) -> dict:
        return {
            "id": self.pk,
            "name": self.name,
            "spec": self.spec,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SavedStrategyTemplate(models.Model):
    """User-saved strategy framework ensemble templates."""

    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=64, blank=True, default="Custom")
    framework = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.name

    def to_dict(self) -> dict:
        return {
            "id": self.pk,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "framework": self.framework,
            "is_system": False,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LiveAccountProfile(models.Model):
    """Non-secret connection metadata; credentials live only in the OS keyring."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=32, default="alpaca")
    data_provider = models.CharField(max_length=32, default="alpaca")
    environment = models.CharField(max_length=16, default="paper")
    display_name = models.CharField(max_length=80, default="Alpaca paper")
    account_identifier = models.CharField(max_length=128, blank=True, default="")
    keyring_service = models.CharField(max_length=160, unique=True)
    keyring_username = models.CharField(max_length=64, default="credentials")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.provider}/{self.environment})"
