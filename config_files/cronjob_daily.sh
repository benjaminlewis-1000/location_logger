#! /bin/sh

# /usr/local/bin/python /project/addpoints_gpx_google.py
# -n (non-blocking): if a backfill_county_visit_years.py run already
# holds the lock, this exits immediately without running anything --
# cron firing again in another hour costs nothing.
flock -n /tmp/county_processing.lock -c "/usr/local/bin/python /project/add_county_visits.py"

