import logging
import os
import paramiko
from django.conf import settings
from datetime import datetime

logger = logging.getLogger("attendance")

def backup_db_to_sftp():
    """
    Backs up the SQLite database to a remote SFTP server.
    """
    db_path = os.path.join(settings.BASE_DIR, "db.sqlite3")
    if not os.path.exists(db_path):
        logger.error("SFTP Backup: db.sqlite3 not found at %s", db_path)
        return

    host = settings.SFTP_HOST
    port = settings.SFTP_PORT
    user = settings.SFTP_USER
    password = settings.SFTP_PASS
    remote_dir = settings.SFTP_REMOTE_DIR

    if not host or not user:
        logger.warning("SFTP Backup: Host or User not configured. Skipping backup.")
        return

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Ensure remote directory exists
        try:
            sftp.chdir(remote_dir)
        except IOError:
            sftp.mkdir(remote_dir)
            sftp.chdir(remote_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_filename = f"db_backup_{timestamp}.sqlite3"

        logger.info("SFTP Backup: Uploading %s to %s", db_path, remote_filename)
        sftp.put(db_path, remote_filename)

        sftp.close()
        transport.close()
        logger.info("SFTP Backup: Successfully uploaded %s", remote_filename)

    except Exception as e:
        logger.error("SFTP Backup Error: %s", str(e))

def send_daily_summary_report():
    """
    Placeholder for a daily summary report email.
    """
    logger.info("Task: Sending daily summary report (Placeholder)")
    # Logic to send email would go here
    pass
