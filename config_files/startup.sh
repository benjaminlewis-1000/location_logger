#! /bin/bash

/usr/sbin/crond

# gunicorn -b 0.0.0.0:5000 test_flask:app &
# /usr/local/bin/python /usr/local/bin/gunicorn -b 0.0.0.0:5000 test_flask:app
/usr/local/bin/python /usr/local/bin/gunicorn -b 0.0.0.0:5000 serve_flask_interface:app
cron

while true; do
    sleep 10
done
