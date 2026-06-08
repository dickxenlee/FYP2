from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_phase3_qa_redesign'),
    ]

    operations = [
        migrations.AddField(
            model_name='testscenario',
            name='user_rating',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
    ]
