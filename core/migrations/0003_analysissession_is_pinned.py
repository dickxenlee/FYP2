from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_analysissession_suggested_requirement'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysissession',
            name='is_pinned',
            field=models.BooleanField(default=False),
        ),
    ]
