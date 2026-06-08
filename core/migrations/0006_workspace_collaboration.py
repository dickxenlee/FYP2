from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_testscenario_user_rating'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Workspace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('workspace_id', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(default='Team Workspace', max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='owned_workspaces',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.CreateModel(
            name='WorkspaceMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[('owner', 'Owner'), ('member', 'Member')],
                    default='member',
                    max_length=20,
                )),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='workspace_memberships',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('workspace', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='memberships',
                    to='core.workspace',
                )),
            ],
            options={
                'unique_together': {('workspace', 'user')},
            },
        ),
        migrations.AddField(
            model_name='analysissession',
            name='workspace',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sessions',
                to='core.workspace',
            ),
        ),
        migrations.AddField(
            model_name='analysissession',
            name='team_notes',
            field=models.TextField(blank=True, default=''),
        ),
    ]
