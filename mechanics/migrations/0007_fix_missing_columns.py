# Generated manually to fix missing columns

from django.db import migrations


def add_missing_columns(apps, schema_editor):
    """Add missing columns if they don't exist."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(mechanics_repairrequest)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add missing columns
        if 'rejected_at' not in columns:
            cursor.execute(
                "ALTER TABLE mechanics_repairrequest "
                "ADD COLUMN rejected_at datetime NULL"
            )
        
        if 'in_transit_at' not in columns:
            cursor.execute(
                "ALTER TABLE mechanics_repairrequest "
                "ADD COLUMN in_transit_at datetime NULL"
            )
        
        if 'in_progress_at' not in columns:
            cursor.execute(
                "ALTER TABLE mechanics_repairrequest "
                "ADD COLUMN in_progress_at datetime NULL"
            )
        
        if 'created_at' not in columns:
            cursor.execute(
                "ALTER TABLE mechanics_repairrequest "
                "ADD COLUMN created_at datetime NULL"
            )
        
        if 'updated_at' not in columns:
            cursor.execute(
                "ALTER TABLE mechanics_repairrequest "
                "ADD COLUMN updated_at datetime NULL"
            )


class Migration(migrations.Migration):

    dependencies = [
        ('mechanics', '0006_repairrequest_created_at_and_more'),
    ]

    operations = [
        migrations.RunPython(add_missing_columns, migrations.RunPython.noop),
    ]
