#! /usr/bin/env python

# Pulls ongoing GPS data from Google Drive, replacing the external
# get_data.sh + host cron this app used to depend on (see CLAUDE.md,
# "In-container Google Drive sync"). Two things this does differently
# from that script, both deliberate:
#
# - Never moves or deletes anything on Drive. get_data.sh moved each
#   file to a second folder once downloaded, to mark it handled -- safe
#   with a single consumer, not safe once more than one environment
#   (dev, prod) polls the same folder independently, since one would
#   move a file the other hasn't seen yet. Content-hash comparison
#   (below) replaces that instead.
# - The watched file is date-named but gets overwritten/appended by the
#   phone app several times a day, so filename alone can't say whether
#   there's new data since the last check -- only its MD5 can.
#
# Downloads land in the same place get_data.sh already used
# (/data/gdrive_data/unprocessed/holding_dir), so addpoints_gpx_google.py's
# existing cron picks them up completely unmodified. Re-processing a
# whole re-downloaded file is safe: location_db.insert_location already
# dedupes by exact utc_time, so only genuinely new points actually insert.

import os
import subprocess

import config
import location_db

database = location_db.locationDB(db_name=config.database_location,
        fips_file=config.county_fips_file,
        country_file=config.country_file)

GDRIVE_BIN = 'gdrive'
DEST_DIR = '/data/gdrive_data/unprocessed/holding_dir'
FIELD_SEP = '|'

# gdrive resolves its account/token storage relative to $HOME/.config
# (confirmed empirically -- it does NOT respect $XDG_CONFIG_HOME despite
# that looking like the right lever from the binary's strings output).
# Left at the container's real HOME (/root), that's outside both bind
# mounts (/data, /project) and would be wiped on a container recreate --
# so every gdrive call here overrides just its own subprocess env,
# rather than redirecting the whole container's HOME and risking
# shifting where other tools cache things.
GDRIVE_HOME = '/data/gdrive_home'


def _run(args, timeout=60):
    env = {**os.environ, 'HOME': GDRIVE_HOME}
    try:
        return subprocess.run([GDRIVE_BIN] + args, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, returncode=1, stdout='', stderr='gdrive command timed out')


def list_files(folder_id):
    result = _run(['files', 'list', '--parent', folder_id, '--skip-header',
            '--max', '100', '--field-separator', FIELD_SEP])
    if result.returncode != 0:
        print(f"gdrive files list failed: {result.stderr.strip()}")
        return []

    files = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(FIELD_SEP)
        if len(parts) < 3:
            continue
        file_id, name, file_type = parts[0], parts[1], parts[2]
        if file_type != 'regular':
            continue
        files.append((file_id, name))
    return files


def get_md5(file_id):
    result = _run(['files', 'info', file_id])
    if result.returncode != 0:
        print(f"gdrive files info failed for {file_id}: {result.stderr.strip()}")
        return None
    for line in result.stdout.splitlines():
        if line.startswith('MD5:'):
            return line.split(':', 1)[1].strip()
    return None


def download_file(file_id):
    os.makedirs(DEST_DIR, exist_ok=True)
    result = _run(['files', 'download', file_id, '--destination', DEST_DIR, '--overwrite'])
    if result.returncode != 0:
        print(f"gdrive files download failed for {file_id}: {result.stderr.strip()}")
        return False
    return True


def main():
    folder = database.get_gdrive_folder()
    if not folder or not folder.get('folder_id'):
        print("No Google Drive folder configured yet -- set one on /engineering.")
        return

    files = list_files(folder['folder_id'])
    if not files:
        print(f"No files found in the watched Drive folder ({folder.get('folder_name')}).")
        return

    for file_id, name in files:
        if not name.lower().endswith('.gpx'):
            continue

        md5 = get_md5(file_id)
        if md5 is None:
            print(f"{name}: could not fetch MD5, skipping")
            continue

        prev = database.get_gdrive_sync_state(file_id)
        if prev and prev['last_md5'] == md5:
            database.record_gdrive_check(file_id, name, md5, changed=False)
            print(f"{name}: unchanged (MD5 {md5})")
            continue

        if download_file(file_id):
            database.record_gdrive_check(file_id, name, md5, changed=True)
            print(f"{name}: new content downloaded (MD5 {md5})")
        else:
            print(f"{name}: download failed, not recording as checked")


if __name__ == '__main__':
    main()
