from celery import shared_task
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)


@shared_task
def maintain_indexes():
    """
    Scheduled task to maintain database indexes.
    Runs index analysis and maintenance operations.
    """
    try:
        # Analyze index usage and bloat
        call_command('monitor_indexes', '--analyze')

        # Run VACUUM ANALYZE on tables
        call_command('monitor_indexes', '--vacuum')

        # Rebuild indexes with high bloat
        call_command('monitor_indexes', '--reindex')

        logger.info("Index maintenance completed successfully")
    except Exception as e:
        logger.error(f"Error during index maintenance: {str(e)}")
        raise


@shared_task
def maintain_asset_indexes():
    """
    Scheduled task to maintain asset-related indexes.
    Runs asset-specific index analysis and maintenance.
    """
    try:
        # Run asset-specific index analysis and maintenance
        call_command('monitor_indexes', '--asset-specific')

        logger.info("Asset index maintenance completed successfully")
    except Exception as e:
        logger.error(f"Error during asset index maintenance: {str(e)}")
        raise
