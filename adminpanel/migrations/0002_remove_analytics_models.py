# Generated manually - Remove analytics models from adminpanel

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('adminpanel', '0001_consolidate_analytics_models'),
    ]

    operations = [
        migrations.DeleteModel(
            name='AnalyticsWidget',
        ),
        migrations.DeleteModel(
            name='AnalyticsReport',
        ),
        migrations.DeleteModel(
            name='UserAnalytics',
        ),
        migrations.DeleteModel(
            name='AnalyticsCache',
        ),
        migrations.DeleteModel(
            name='AnalyticsDashboard',
        ),
    ]
