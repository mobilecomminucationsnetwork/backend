# Generated by Django 5.2.1 on 2025-05-15 13:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_facevector'),
    ]

    operations = [
        migrations.AddField(
            model_name='facevector',
            name='face_image_base64',
            field=models.TextField(blank=True, null=True),
        ),
    ]
