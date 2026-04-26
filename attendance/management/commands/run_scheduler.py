import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution
from django_apscheduler import util

from attendance.tasks import backup_db_to_sftp, send_daily_summary_report

logger = logging.getLogger("attendance")

@util.close_old_connections
def delete_old_job_executions(max_age=604_800):
    """
    This job deletes APScheduler job execution entries from the database every week.
    It helps keep the database size manageable.
    :param max_age: The maximum length of time to retain old job execution records (in seconds).
    """
    DjangoJobExecution.objects.delete_old_job_executions(max_age)

class Command(BaseCommand):
    help = "Runs APScheduler for background tasks (SFTP backups, reports, etc.)"

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), "default")

        # 1. SFTP Backup - Every day at 02:00 AM
        scheduler.add_job(
            backup_db_to_sftp,
            trigger=CronTrigger(hour="02", minute="00"),
            id="backup_db_to_sftp",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Added job 'backup_db_to_sftp'.")

        # 2. Daily Summary Report - Every day at 09:00 PM
        scheduler.add_job(
            send_daily_summary_report,
            trigger=CronTrigger(hour="21", minute="00"),
            id="send_daily_summary_report",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Added job 'send_daily_summary_report'.")

        # 3. Cleanup Job Executions - Every week
        scheduler.add_job(
            delete_old_job_executions,
            trigger=CronTrigger(day_of_week="mon", hour="00", minute="00"),
            id="delete_old_job_executions",
            max_instances=1,
            replace_existing=True,
        )
        logger.info("Added weekly cleanup job.")

        try:
            logger.info("Starting scheduler...")
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Stopping scheduler...")
            scheduler.shutdown()
            logger.info("Scheduler shut down successfully!")
