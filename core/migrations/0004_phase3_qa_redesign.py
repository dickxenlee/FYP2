from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_analysissession_is_pinned'),
    ]

    operations = [
        # New fields on AnalysisSession
        migrations.AddField(
            model_name='analysissession',
            name='requirement_id',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='analysissession',
            name='extracted_info',
            field=models.TextField(blank=True, default='{}'),
        ),
        migrations.AddField(
            model_name='analysissession',
            name='clarity_score',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysissession',
            name='completeness_score',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysissession',
            name='testability_score',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='analysissession',
            name='severity',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
        # New fields on TestScenario
        migrations.AddField(
            model_name='testscenario',
            name='requirement_ref',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='testscenario',
            name='condition_ref',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
        migrations.AddField(
            model_name='testscenario',
            name='priority',
            field=models.CharField(
                choices=[('High', 'High'), ('Medium', 'Medium'), ('Low', 'Low')],
                default='Medium',
                max_length=10,
            ),
        ),
        # New model: TestCondition
        migrations.CreateModel(
            name='TestCondition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('condition_id', models.CharField(max_length=10)),
                ('description', models.TextField()),
                ('condition_type', models.CharField(
                    choices=[
                        ('Positive', 'Positive'), ('Negative', 'Negative'),
                        ('Boundary', 'Boundary'), ('Security', 'Security'),
                        ('Performance', 'Performance'),
                    ],
                    max_length=20,
                )),
                ('priority', models.CharField(
                    choices=[('High', 'High'), ('Medium', 'Medium'), ('Low', 'Low')],
                    default='Medium',
                    max_length=10,
                )),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='test_conditions',
                    to='core.analysissession',
                )),
            ],
        ),
        # New model: RequirementGap
        migrations.CreateModel(
            name='RequirementGap',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('issue_id', models.CharField(max_length=10)),
                ('issue_type', models.CharField(max_length=50)),
                ('description', models.TextField()),
                ('suggested_clarification', models.TextField()),
                ('session', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='gaps',
                    to='core.analysissession',
                )),
            ],
        ),
        # New model: DetailedTestCase
        migrations.CreateModel(
            name='DetailedTestCase',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('test_data', models.TextField(blank=True, default='')),
                ('steps_json', models.TextField(default='[]')),
                ('expected_results', models.TextField(blank=True, default='')),
                ('postconditions', models.TextField(blank=True, default='')),
                ('scenario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='detailed_case',
                    to='core.testscenario',
                )),
            ],
        ),
    ]
