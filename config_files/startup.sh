#! /bin/bash

/usr/local/bin/python /usr/local/bin/gunicorn -b 0.0.0.0:5000 serve_flask_interface:app &

# Cron (GPS/county-visit ingestion) should only ever run against the
# real prod data -- APP_ENV=dev is set in dev's docker-compose.yml only,
# so this is a no-op there by default (prod never sets APP_ENV, so it
# keeps running cron with no change needed on that side).
if [ "$APP_ENV" != "dev" ]; then
    cron &
else
    echo "APP_ENV=dev -- skipping cron startup"
fi

while true; do
    sleep 10
done
