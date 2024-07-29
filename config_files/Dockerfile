#FROM python:3.11-alpine
FROM python:3.11-slim-bookworm

WORKDIR /project

RUN apt update && apt install -y g++ libgeos-dev libgdal-dev wget 
# RUN pip install numpy
# RUN pip install pandas
# RUN pip install scikit-learn
# RUN apk add geos-dev
# RUN pip install shapely
# RUN pip install cartopy

#RUN apk update && \
#    apk add gdal-dev # binutils libproj-dev gdal-bin ffmpeg libgdal-dev

# RUN pip install fiona

ADD config_files/requirements.txt /project
RUN pip install -r requirements.txt

# RUN apt install -y wget
# flask-googlemaps has an issue with a template. Reinstall a later version
# RUN python3 -m pip install https://github.com/flask-extensions/Flask-GoogleMaps/archive/refs/tags/0.4.1.1.tar.gz
RUN wget https://github.com/flask-extensions/Flask-GoogleMaps/archive/refs/tags/0.4.1.1.tar.gz -O /flask.tar.gz
WORKDIR /
RUN tar xvf flask.tar.gz
# RUN pip install flask-googlemaps>=0.4.1.1

RUN cp /Flask-GoogleMaps-0.4.1.1/flask_googlemaps/*  /usr/local/lib/python3.11/site-packages/flask_googlemaps -R 

WORKDIR /project

ADD config_files/cronjob.sh /etc/periodic/15min/cronjob.sh
RUN chmod a+x /etc/periodic/15min/cronjob.sh

ADD config_files/startup.sh /project
RUN apt install procps bash-completion -y

RUN rm -rf /var/lib/apt/lists/* && apt clean
