import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("api", "0002_savedstrategytemplate")]

    operations = [
        migrations.CreateModel(
            name="LiveAccountProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("provider", models.CharField(default="alpaca", max_length=32)),
                ("environment", models.CharField(default="paper", max_length=16)),
                ("display_name", models.CharField(default="Alpaca paper", max_length=80)),
                ("account_identifier", models.CharField(blank=True, default="", max_length=128)),
                ("keyring_service", models.CharField(max_length=160, unique=True)),
                ("keyring_username", models.CharField(default="credentials", max_length=64)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.AddConstraint(
            model_name="liveaccountprofile",
            constraint=models.UniqueConstraint(fields=("provider", "environment"), name="uniq_live_account_provider_env"),
        ),
    ]
