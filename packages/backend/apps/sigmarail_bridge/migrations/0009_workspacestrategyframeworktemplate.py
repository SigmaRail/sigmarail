import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sigmarail_bridge", "0008_user_owned_strategy_and_screens"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceStrategyFrameworkTemplate",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("description", models.TextField(blank=True, default="")),
                ("category", models.CharField(default="Custom", max_length=64)),
                ("framework", models.JSONField()),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_sigmarail_framework_templates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "owner_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="owned_sigmarail_framework_templates",
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
            options={"ordering": ["-updated_at", "name"]},
        ),
        migrations.AddConstraint(
            model_name="workspacestrategyframeworktemplate",
            constraint=models.UniqueConstraint(
                models.functions.Lower("name"),
                models.F("tenant"),
                models.F("owner_user"),
                name="sigmarail_template_unique_name_per_owner",
            ),
        ),
    ]
