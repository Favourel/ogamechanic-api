# Generated manually to fix missing columns

from django.db import migrations


def add_missing_columns(apps, schema_editor):
    """Add missing columns if they don't exist."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Get database vendor (postgresql, sqlite, mysql, etc.)
        db_vendor = connection.vendor
        
        # Check if columns exist based on database type
        if db_vendor == 'sqlite':
            cursor.execute("PRAGMA table_info(mechanics_repairrequest)")
            columns = [row[1] for row in cursor.fetchall()]
        elif db_vendor == 'postgresql':
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'mechanics_repairrequest'
            """)
            columns = [row[0] for row in cursor.fetchall()]
        elif db_vendor == 'mysql':
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'mechanics_repairrequest' 
                AND TABLE_SCHEMA = DATABASE()
            """)
            columns = [row[0] for row in cursor.fetchall()]
        else:
            # For other databases, try to add columns and ignore errors
            columns = []
        
        # Determine the correct datetime type based on database
        if db_vendor == 'postgresql':
            datetime_type = 'TIMESTAMP'
        elif db_vendor == 'mysql':
            datetime_type = 'DATETIME'
        else:  # sqlite and others
            datetime_type = 'datetime'
        
        # Add missing columns
        if 'rejected_at' not in columns:
            try:
                cursor.execute(
                    f"ALTER TABLE mechanics_repairrequest "
                    f"ADD COLUMN rejected_at {datetime_type} NULL"
                )
            except Exception:
                pass  # Column might already exist
        
        if 'in_transit_at' not in columns:
            try:
                cursor.execute(
                    f"ALTER TABLE mechanics_repairrequest "
                    f"ADD COLUMN in_transit_at {datetime_type} NULL"
                )
            except Exception:
                pass
        
        if 'in_progress_at' not in columns:
            try:
                cursor.execute(
                    f"ALTER TABLE mechanics_repairrequest "
                    f"ADD COLUMN in_progress_at {datetime_type} NULL"
                )
            except Exception:
                pass
        
        if 'created_at' not in columns:
            try:
                cursor.execute(
                    f"ALTER TABLE mechanics_repairrequest "
                    f"ADD COLUMN created_at {datetime_type} NULL"
                )
            except Exception:
                pass
        
        if 'updated_at' not in columns:
            try:
                cursor.execute(
                    f"ALTER TABLE mechanics_repairrequest "
                    f"ADD COLUMN updated_at {datetime_type} NULL"
                )
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('mechanics', '0006_repairrequest_created_at_and_more'),
    ]

    operations = [
        migrations.RunPython(add_missing_columns, migrations.RunPython.noop),
    ]
