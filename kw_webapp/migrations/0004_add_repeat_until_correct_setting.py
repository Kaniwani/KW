from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kw_webapp', '0003_vocabulary_manual_reading_whitelist'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='repeat_until_correct',
            field=models.BooleanField(default=False),
        ),
    ]
