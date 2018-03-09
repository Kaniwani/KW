# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-11-25 18:21
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('kw_webapp', '0028_report'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='report',
            name='vocabulary',
        ),
        migrations.AddField(
            model_name='report',
            name='reading',
            field=models.ForeignKey(default=0, on_delete=django.db.models.deletion.CASCADE, to='kw_webapp.Reading'),
            preserve_default=False,
        ),
    ]
