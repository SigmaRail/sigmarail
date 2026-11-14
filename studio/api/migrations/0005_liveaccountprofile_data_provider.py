from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0004_multiple_live_account_profiles")]

    operations = [
        migrations.AddField(
            model_name="liveaccountprofile",
            name="data_provider",
            field=models.CharField(default="alpaca", max_length=32),
        ),
    ]
