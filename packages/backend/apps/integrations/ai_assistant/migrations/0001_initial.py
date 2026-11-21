from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="MCPUserIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("issuer", models.URLField(max_length=512)),
                ("subject", models.CharField(max_length=512)),
                ("email", models.EmailField(max_length=255)),
                ("linked_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"verbose_name": "MCP user identity", "verbose_name_plural": "MCP user identities"},
        ),
        migrations.AddConstraint(
            model_name="mcpuseridentity",
            constraint=models.UniqueConstraint(fields=("issuer", "subject"), name="unique_mcp_issuer_subject"),
        ),
    ]
