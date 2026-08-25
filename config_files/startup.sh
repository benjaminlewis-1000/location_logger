#! /bin/bash

/usr/local/bin/python /usr/local/bin/gunicorn --reload -b 0.0.0.0:5000 serve_flask_interface:app &

# Cron (GPS/county-visit ingestion) should only ever run against the
# real prod data -- APP_ENV=dev is set in dev's docker-compose.yml only,
# so this is a no-op there by default (prod never sets APP_ENV, so it
# keeps running cron with no change needed on that side).
if [ "$APP_ENV" != "dev" ]; then
    cron &
else
    echo "APP_ENV=dev -- skipping cron startup"
fi

# Dev-only convenience, separate from the cron gate above: the Google
# Drive sync (sync_gdrive_gps.py) is exercised against real data here at
# a real, frequent cadence, rather than staying dormant like the other
# two cron jobs. Additive -- doesn't touch the cron daemon or those two
# jobs' own dev-off behavior. Prod gets this job through the normal
# cron-config entry instead, once cut over.
if [ "$APP_ENV" = "dev" ]; then
    ( while true; do
        /usr/local/bin/python /project/sync_gdrive_gps.py
        sleep 900
    done ) &
fi

while true; do
    sleep 10
done
