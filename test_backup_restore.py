"""
Restore-verification check for backup_database.py. Not wired into any CI
(this repo has no test suite/runner -- see CLAUDE.md) -- run manually
after touching the backup script, or periodically as a real restore
drill: `docker exec -w /project location_track python3 test_backup_restore.py`.

Takes a fresh backup via backup_database.main(), decompresses it, and
checks the result is actually a usable, uncorrupted database -- not just
that the compress/write step exited 0. Specifically:
  1. `PRAGMA integrity_check` passes (catches truncation/corruption that a
     plain "did sqlite3.connect() not raise" check would miss).
  2. Every table that exists in the live DB also exists in the restored
     one, with an identical row count (run immediately after the backup,
     so the two should match exactly -- a real-world restore of an older
     backup will legitimately have fewer rows, but a same-moment backup
     should not).
Exits non-zero on any failure, so this is scriptable (e.g. wrap in cron
to actually alert on a broken backup, not just assume one worked).
"""

import os
import sqlite3
import subprocess
import sys
import tempfile

import config
import backup_database


def restore_to_tmp(backup_path, tmp_path):
    subprocess.run(['zstd', '-d', '-f', backup_path, '-o', tmp_path], check=True)


def check_integrity(db_path):
    conn = sqlite3.connect(db_path)
    try:
        result = conn.execute('PRAGMA integrity_check').fetchall()
    finally:
        conn.close()
    ok = result == [('ok',)]
    if not ok:
        print(f'FAIL: integrity_check returned {result}')
    return ok


def check_row_counts_match(live_path, restored_path):
    live = sqlite3.connect(live_path)
    restored = sqlite3.connect(restored_path)
    try:
        live_tables = {
            r[0] for r in live.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        restored_tables = {
            r[0] for r in restored.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if live_tables != restored_tables:
            print(f'FAIL: table sets differ. Live-only: {live_tables - restored_tables}, '
                  f'restored-only: {restored_tables - live_tables}')
            return False

        all_ok = True
        for table in sorted(live_tables):
            live_count = live.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            restored_count = restored.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if live_count != restored_count:
                print(f'FAIL: {table} row count differs -- live={live_count} '
                      f'restored={restored_count}')
                all_ok = False
            else:
                print(f'  OK: {table} ({live_count} rows)')
        return all_ok
    finally:
        restored.close()
        live.close()


def main():
    print('Taking a fresh backup...')
    backup_database.main()

    today_filename = f'location_{backup_database.datetime.datetime.now(backup_database.datetime.timezone.utc).strftime("%Y-%m-%d")}.sqlite.zst'
    backup_path = os.path.join(config.backup_dir, 'daily', today_filename)
    if not os.path.exists(backup_path):
        print(f'FAIL: expected backup at {backup_path}, not found')
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        print(f'Restoring {backup_path} -> {tmp_path}...')
        restore_to_tmp(backup_path, tmp_path)

        print('Checking integrity...')
        integrity_ok = check_integrity(tmp_path)

        print('Comparing row counts against the live DB...')
        counts_ok = check_row_counts_match(config.database_location, tmp_path)
    finally:
        os.remove(tmp_path)

    if integrity_ok and counts_ok:
        print('PASS: backup restores cleanly and matches the live DB.')
        sys.exit(0)
    else:
        print('FAIL: see above.')
        sys.exit(1)


if __name__ == '__main__':
    main()
