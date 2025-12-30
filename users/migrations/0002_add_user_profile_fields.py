# Generated migration to add profile fields to User model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True, verbose_name='date of birth'),
        ),
        migrations.AddField(
            model_name='user',
            name='gender',
            field=models.CharField(
                blank=True,
                choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
                max_length=10,
                null=True,
                verbose_name='gender'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='profile_picture',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='users/profile_pictures/',
                verbose_name='profile picture'
            ),
        ),
    ]
