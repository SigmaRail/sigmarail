import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sigmarail_bridge", "0005_workspacedeploymentreference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("multitenancy", "0023_alter_permission_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceBrokerAccountReference",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("profile_id", models.CharField(max_length=255, unique=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_sigmarail_broker_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        blank=True,
                        null=True,
                        related_name="%(class)s_set",
                        to="multitenancy.tenant",
                        verbose_name="Tenant",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
