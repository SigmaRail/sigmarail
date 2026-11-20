from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sigmarail_bridge", "0006_workspacebrokeraccountreference"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspacebrokeraccountreference",
            name="provider",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="workspacebrokeraccountreference",
            name="data_provider",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="workspacebrokeraccountreference",
            name="environment",
            field=models.CharField(default="paper", max_length=16),
        ),
        migrations.AddField(
            model_name="workspacebrokeraccountreference",
            name="display_name",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="workspacebrokeraccountreference",
            name="account_identifier",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="workspacebrokeraccountreference",
            name="active",
            field=models.BooleanField(default=True),
        ),
    ]
