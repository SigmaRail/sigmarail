from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sigmarail_bridge", "0009_workspacestrategyframeworktemplate")]

    operations = [
        migrations.AddField("workspacestrategyreference", "title", models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField("workspacestrategyreference", "spec", models.JSONField(blank=True, null=True)),
        migrations.AddField("workspacestrategyreference", "pipeline_document", models.JSONField(blank=True, null=True)),
        migrations.AddField("workspacestrategyreference", "notes", models.TextField(blank=True, default="")),
        migrations.AddField("workspacestrategyreference", "category", models.CharField(blank=True, default="", max_length=80)),
        migrations.AddField("workspacestrategyreference", "tags", models.JSONField(blank=True, default=list)),
        migrations.AddField("workspacestrategyreference", "spec_schema_version", models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField("workspacestrategyreference", "content_hash", models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField("workspacestrategyreference", "compiler_version", models.CharField(blank=True, default="", max_length=80)),
        migrations.AddField("workspacestrategyreference", "parent_ir_id", models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField("workspacestrategyreference", "parent_content_hash", models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField("workspacestrategyreference", "mutation_type", models.CharField(blank=True, default="init", max_length=32)),
        migrations.AddField("workspacestrategyreference", "changelog_notes", models.TextField(blank=True, default="")),
        migrations.AddField("workspacestrategyreference", "is_template", models.BooleanField(default=False)),
        migrations.AddField("workspacebacktestreference", "strategy_content_hash", models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField("workspacebacktestreference", "strategy_snapshot", models.JSONField(blank=True, null=True)),
        migrations.AddField("workspacebacktestreference", "configuration", models.JSONField(blank=True, default=dict)),
        migrations.AddField("workspacebacktestreference", "status", models.CharField(default="pending", max_length=24)),
        migrations.AddField("workspacebacktestreference", "progress", models.JSONField(blank=True, default=dict)),
        migrations.AddField("workspacebacktestreference", "result_summary", models.JSONField(blank=True, null=True)),
        migrations.AddField("workspacebacktestreference", "error_message", models.TextField(blank=True, default="")),
        migrations.AddField("workspaceoptimizerreference", "base_strategy_content_hash", models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField("workspaceoptimizerreference", "configuration", models.JSONField(blank=True, default=dict)),
        migrations.AddField("workspaceoptimizerreference", "status", models.CharField(default="pending", max_length=24)),
        migrations.AddField("workspaceoptimizerreference", "result_summary", models.JSONField(blank=True, null=True)),
        migrations.AddField("workspacedeploymentreference", "strategy_content_hash", models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField("workspacedeploymentreference", "approval_run_id", models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField("workspacedeploymentreference", "configuration", models.JSONField(blank=True, default=dict)),
        migrations.AddField("workspacedeploymentreference", "status", models.CharField(default="pending", max_length=24)),
        migrations.AddField("workspacedeploymentreference", "stopped_at", models.DateTimeField(blank=True, null=True)),
    ]
