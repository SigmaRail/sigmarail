from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_alter_useravatar_original_alter_useravatar_thumbnail"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="appearance",
            field=models.CharField(
                choices=[("light", "Light"), ("dark", "Dark"), ("system", "System")],
                default="system",
                help_text="User's preferred color appearance across devices",
                max_length=10,
            ),
        ),
    ]
