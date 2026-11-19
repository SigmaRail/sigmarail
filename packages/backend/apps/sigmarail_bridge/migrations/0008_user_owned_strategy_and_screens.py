from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_creator_to_owner(apps, schema_editor):
    WorkspaceScreen = apps.get_model("sigmarail_bridge", "WorkspaceScreen")
    WorkspaceStrategyReference = apps.get_model("sigmarail_bridge", "WorkspaceStrategyReference")
    WorkspaceScreen.objects.filter(owner_user__isnull=True, created_by__isnull=False).update(
        owner_user_id=models.F("created_by_id")
    )
    WorkspaceStrategyReference.objects.filter(owner_user__isnull=True, created_by__isnull=False).update(
        owner_user_id=models.F("created_by_id")
    )
    WorkspaceScreen.objects.filter(owner_user__isnull=True).update(is_shared=True)
    WorkspaceStrategyReference.objects.filter(owner_user__isnull=True).update(is_shared=True)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sigmarail_bridge", "0007_workspacebrokeraccount_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspacescreen",
            name="owner_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_sigmarail_screens",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workspacescreen",
            name="is_shared",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="workspacestrategyreference",
            name="owner_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="owned_sigmarail_strategies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workspacestrategyreference",
            name="is_shared",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(copy_creator_to_owner, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="workspacescreen",
            name="sigmarail_screen_unique_name_per_tenant",
        ),
        migrations.AddConstraint(
            model_name="workspacescreen",
            constraint=models.UniqueConstraint(
                fields=("tenant", "owner_user", "name"),
                name="sigmarail_screen_unique_name_per_owner",
            ),
        ),
    ]
