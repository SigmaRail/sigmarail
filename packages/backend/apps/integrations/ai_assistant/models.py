from django.conf import settings
from django.db import models


class MCPUserIdentity(models.Model):
    """A verified remote OAuth identity linked to an existing AppTension user."""

    issuer = models.URLField(max_length=512)
    subject = models.CharField(max_length=512)
    email = models.EmailField(max_length=255)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_identities",
    )
    linked_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("issuer", "subject"), name="unique_mcp_issuer_subject"),
        ]
        verbose_name = "MCP user identity"
        verbose_name_plural = "MCP user identities"

    def __str__(self):
        return f"{self.issuer} / {self.subject} → {self.user_id}"
