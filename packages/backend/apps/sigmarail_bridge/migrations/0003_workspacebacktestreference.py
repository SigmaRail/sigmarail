import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("multitenancy", "0023_alter_permission_category"),
        ("sigmarail_bridge", "0002_workspacestrategyreference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceBacktestReference",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("job_id", models.CharField(max_length=255, unique=True)),
                ("run_id", models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ("ir_id", models.CharField(max_length=255)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_sigmarail_backtests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_set",
                        to="multitenancy.tenant",
                        verbose_name="Tenant",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
