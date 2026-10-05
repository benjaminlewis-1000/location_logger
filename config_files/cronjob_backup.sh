#! /bin/sh

# Own lock, separate from the other cron locks -- this only reads the DB
# via sqlite3's backup API (safe concurrently with live writes) and
# writes to the unrelated /backups mount.
flock -n /tmp/backup_processing.lock -c "/usr/local/bin/python /project/backup_database.py"
