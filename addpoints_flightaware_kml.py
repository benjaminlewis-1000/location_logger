
#import config
#from calendar import timegm
#from datetime import datetime, timedelta
#from flask import Flask, request, Response, session, redirect, render_template, request, abort, jsonify
#from flask_session import Session
#from sqlalchemy import create_engine
#from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float
#from sqlalchemy.sql import select
#import dateutil
#import dateutil.parser
#import flask
#import geocoder
#import json
#import jsonpickle
#import math
#import os
#import random
#import re
#import requests
#import sqlalchemy
#import time
#import csv
#import urllib

from datetime import datetime, timedelta, timezone
import xmltodict
import datetime
import config
import time
import dateutil.parser
import pytz

import location_db


current_timezone = pytz.timezone("US/Eastern")
print(current_timezone)

database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file, country_file=config.country_file)
uuid = database.get_user_id('ben')


with open('FlightAware_AAL48_KDFW_LFPG_20250201.kml', 'r') as fh:
	data = fh.read()

data = xmltodict.parse(data)

when = data['kml']['Document']['Placemark'][2]['gx:Track']['when']
where = data['kml']['Document']['Placemark'][2]['gx:Track']['gx:coord']

assert len(when) == len(where)



for ptidx in range(len(when)):
    zulutime = when[ptidx]
    loc = where[ptidx]
    lon, lat, alt = loc.split(' ')
    lat = float(lat)
    lon = float(lon)
    alt = float(alt)
    timeiso = dateutil.parser.isoparse(zulutime)
    print(zulutime)
    print(timeiso)
    print(int(timeiso.strftime('%s')))
    print(timeiso.tzinfo, zulutime)
#    current_timezone.localize(timeiso)
#    timeiso.localize(current_timezone)
    timeiso.replace(tzinfo=current_timezone) # ZoneInfo("America/Los_Angeles"))
    timeiso = timeiso -  timedelta(hours=5) #minutes=50)
#    timeiso.replace(tzinfo=timezone.utc).astimezone(tz='America/New_York')
    utc_time = int(timeiso.strftime('%s'))
    print(utc_time)
    exit()

    pos_data = {}
    pos_data['uuid'] = uuid
    pos_data['dev_id'] = 'ben'
    pos_data['utc'] = utc_time
    pos_data['lat'] = lat
    pos_data['lon'] = lon
    pos_data['battery'] = -1
    pos_data['accuracy'] = -1
    pos_data['date'] = timeiso
    pos_data['altitude'] = alt 
    pos_data['speed'] = 0
    pos_data['source'] = 'hist'

    print(pos_data)
    database.insert_location(pos_data)
