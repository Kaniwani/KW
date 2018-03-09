# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-12-10 23:46
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('kw_webapp', '0029_auto_20171125_1321'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='reading',
            unique_together=set([('character', 'kana')]),
        ),
        migrations.AlterUniqueTogether(
            name='userspecific',
            unique_together=set([('vocabulary', 'user')]),
        ),
    ]
