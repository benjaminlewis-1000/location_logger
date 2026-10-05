"""
Nightly SQLite backup with daily/weekly retention. Cron entry point --
see cronjob_backup.sh (flock-wrapped) and config_files/cron-config.

Takes a consistent snapshot via sqlite3's backup API (safe to run against
the live DB while gunicorn has it open -- this is exactly what that API
is for, unlike a plain file copy which could catch a write mid-flight),
compresses it with zstd, and writes it into config.backup_dir/daily.
On Sundays, that same compressed snapshot is also copied into
config.backup_dir/weekly. Each of the two folders is then pruned to its
own retention count, independent of the other.
"""

import datetime
import os
import shutil
import sqlite3
import subprocess

import config

DAILY_RETENTION = 7
WEEKLY_RETENTION = 4
WEEKLY_PROMOTION_WEEKDAY = 6  # Sunday (datetime.weekday(): Mon=0 .. Sun=6)


def _snapshot_to_tmp(tmp_path):
    source = sqlite3.connect(config.database_location)
    dest = sqlite3.connect(tmp_path)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()


def _compress(tmp_path, dest_path):
    subprocess.run(['zstd', '-f', tmp_path, '-o', dest_path], check=True)


def _prune(directory, keep):
    files = sorted(
        f for f in os.listdir(directory)
        if f.startswith('location_') and f.endswith('.sqlite.zst')
    )
    for stale in files[:-keep] if len(files) > keep else []:
        os.remove(os.path.join(directory, stale))


def main():
    daily_dir = os.path.join(config.backup_dir, 'daily')
    weekly_dir = os.path.join(config.backup_dir, 'weekly')
    os.makedirs(daily_dir, exist_ok=True)
    os.makedirs(weekly_dir, exist_ok=True)

    today = datetime.datetime.now(datetime.timezone.utc)
    filename = f'location_{today.strftime("%Y-%m-%d")}.sqlite.zst'
    daily_path = os.path.join(daily_dir, filename)

    tmp_path = os.path.join(config.backup_dir, f'.tmp_{filename}.sqlite')
    try:
        _snapshot_to_tmp(tmp_path)
        _compress(tmp_path, daily_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    if today.weekday() == WEEKLY_PROMOTION_WEEKDAY:
        shutil.copy2(daily_path, os.path.join(weekly_dir, filename))

    _prune(daily_dir, DAILY_RETENTION)
    _prune(weekly_dir, WEEKLY_RETENTION)

    print(f'Backup complete: {daily_path}')


if __name__ == '__main__':
    main()
