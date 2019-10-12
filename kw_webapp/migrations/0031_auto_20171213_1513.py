# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-12-13 20:13
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("kw_webapp", "0030_auto_20171210_1846")]

    operations = [
        migrations.AlterUniqueTogether(
            name="answersynonym",
            unique_together=set([("character", "kana", "review")]),
        ),
        migrations.AlterUniqueTogether(
            name="meaningsynonym", unique_together=set([("text", "review")])
        ),
    ]
