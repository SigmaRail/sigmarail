from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_userprofile_appearance"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="chart_preferences",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="User's SigmaRail chart display preferences",
            ),
        ),
    ]
