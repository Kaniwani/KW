# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2016-12-11 22:01
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('kw_webapp', '0017_auto_20161125_0916'),
    ]

    operations = [
        migrations.AlterField(
            model_name='answersynonym',
            name='review',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='answer_synonyms', to='kw_webapp.UserSpecific'),
        ),
        migrations.AlterField(
            model_name='profile',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='reading',
            name='vocabulary',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='readings', to='kw_webapp.Vocabulary'),
        ),
        migrations.AlterField(
            model_name='userspecific',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to=settings.AUTH_USER_MODEL),
        ),
    ]
