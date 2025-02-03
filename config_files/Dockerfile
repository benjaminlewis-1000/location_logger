#FROM python:3.11-alpine
FROM python:3.12-slim-bookworm

WORKDIR /project

##################################
# Install apt and pip packages
##################################
RUN apt update && apt install -y g++ libgeos-dev libgdal-dev wget cron procps bash-completion

ADD config_files/requirements.txt /project

RUN pip install -r requirements.txt


##############################
# flask-googlemaps has an issue with a template. Reinstall a later version
##############################
RUN wget https://github.com/flask-extensions/Flask-GoogleMaps/archive/refs/tags/0.4.1.1.tar.gz -O /flask.tar.gz
WORKDIR /
RUN tar xvf flask.tar.gz
RUN cp /Flask-GoogleMaps-0.4.1.1/flask_googlemaps/*  /usr/local/lib/python3.12/site-packages/flask_googlemaps -R 

WORKDIR /project

#######################
# Add cron jobs
#######################
ADD config_files/cronjob_15_min.sh /etc/periodic/cronjob_15_min.sh
ADD config_files/cronjob_daily.sh /etc/periodic/cronjob_daily.sh

RUN chmod a+x /etc/periodic/cronjob_15_min.sh
RUN chmod a+x /etc/periodic/cronjob_daily.sh

ADD config_files/cron-config /etc/cron.d/cron-config
RUN chmod 0644 /etc/cron.d/cron-config
RUN crontab /etc/cron.d/cron-config
RUN touch /var/log/cron.log

#######################
# Add the startup file
#######################
ADD config_files/startup.sh /project

#########################
# Cleanup
#########################
RUN rm -rf /var/lib/apt/lists/* && apt clean
