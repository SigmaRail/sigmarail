from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("api", "0003_liveaccountprofile")]

    operations = [
        migrations.RemoveConstraint(
            model_name="liveaccountprofile",
            name="uniq_live_account_provider_env",
        ),
    ]
