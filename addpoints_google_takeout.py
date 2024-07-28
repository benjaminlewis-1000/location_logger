
from calendar import timegm
from datetime import datetime, timedelta
from flask import Flask, request, Response, session, redirect, render_template, request, abort, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float
from sqlalchemy.sql import select
import dateutil
import dateutil.parser
from json import JSONDecoder
from functools import partial
import flask
import geocoder
import json
import jsonpickle
import math
import os
import random
import re
import requests
import sqlalchemy
import time
import urllib
import location_db
import config

database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)

# USGS Elevation Point Query Service
url = r'https://nationalmap.gov/epqs/pqs.php?'

def elevation_function(lat, lon):

    # define rest query params
    params = {
        'output': 'json',
        'x': lon,
        'y': lat,
        'units': 'Meters'
    }

    # format query string and return query value
    result = requests.get((url + urllib.parse.urlencode(params)))
    print(dir(result))
    print(result.text)
    print("------------")
    return result.json()['USGS_Elevation_Point_Query_Service']['Elevation_Query']['Elevation']



def json_parse(fileobj, decoder=JSONDecoder(), buffersize=2048, seek_offset = None):
    # Reads a file object a chunk at a time. Got the code from
    # stackoverflow initially, but tailored it for this particular
    # style of JSON file, which is fundamentally one giant list of 
    # JSON objects. When doing the raw_decode, it doesn't strip out
    # the comma separating the list elements, so we do that 
    # after each raw_decode as well as every time a chunk is appended
    # to the buffer.

    buffer = ''

    # Allow us to start at an offset.
    if type(seek_offset) is int:
        fileobj.seek(seek_offset)
        buffer = fileobj.read(1000000)
        offset = re.search('{\n.*"lat', buffer).span(0)[0]
        buffer = buffer[offset:]

    for chunk in iter(partial(fileobj.read, buffersize), ''):
        # Read chunks of buffersize. Take out the start of the JSON 
        # list (only needs to be done once, but it's a cheap enough
        # operation) as well as leading commas. 
         chunk = re.sub('\{\n  "locations": \[', '', chunk)
         buffer += chunk
         buffer = re.sub('^, ', '', buffer)

         while buffer:
             try:
                # Try to do a raw_decode, which finds the
                # next fully-formed JSON object. Luckily
                # this works on parts of the list. Finds interpretable
                # JSON and the index it goes to, then truncates
                # the buffer to remove the JSON it just decoded and 
                # yields the resulting JSON dictionary. 
                # Iterates until the buffer no longer contains
                # interpretable JSON. 
                 result, index = decoder.raw_decode(buffer)
                 yield result
                 buffer = buffer[index:].lstrip()
                 # Strip those leading commas. 
                 buffer = re.sub('^, ', '', buffer)
             except ValueError:
                 # Not enough data to decode, read more
                 
                 if len(buffer) > 800000:
                    # The Google location history JSON
                    # ends up having some very long 
                    # JSON elements with activity detection.
                    # Ugh. 
                    print(buffer)
                    print('=========================')
                    print(repr(buffer))
                    exit()
                 break


if __name__ == "__main__":

    # Only start looking at data after this
    # date. 
    first_date = '2013-04-04T18:00:00'
    # first_date = '2023-04-04T18:00:00'

    
    last_was_home = False
    done = 0

    with open('Records.json', 'r') as infh:
        for data_item in json_parse(infh, seek_offset=813260000):

            print(data_item['timestamp'])
            if data_item['timestamp'] < first_date:
                continue
            # Else:
            # print(data, "\n----")
            # process object

            try:
                date_data = datetime.strptime(data_item['timestamp'], "%Y-%m-%dT%H:%M:%S.%fZ")
            except ValueError:
                date_data = datetime.strptime(data_item['timestamp'], "%Y-%m-%dT%H:%M:%SZ")

            utc = time.mktime(date_data.timetuple())
            lat = float(data_item['latitudeE7'] * 1e-7)
            lon = float(data_item['longitudeE7'] * 1e-7)
            print(f"Progress: {done}, {data_item['timestamp']}")
            done += 1

            # Exclude locations around my home. Get one single 
            # point included, and then no more. 
            if lon > -84.06956668951612 and \
                lon < -84.06593487601869 and \
                lat < 39.742379436662816 and \
                lat > 39.74013324157781:
                print("Home!", lat, lon, last_was_home)
                if last_was_home:
                    continue
                last_was_home = True
            else:
                last_was_home = False

            if 'altitude' in data_item.keys():
                alt = float(data_item['altitude'])
            else:
                alt = 0


            uid_dict = {}
            user_id = 'ben'
            if user_id in uid_dict.keys():
                uuid = uid_dict[user_id]
            else:
                uuid = database.get_user_id(user_id)
                uid_dict[user_id] = uuid
        
            pos_data = {}
            pos_data['uuid'] = uuid
            pos_data['dev_id'] = user_id
            pos_data['utc'] = utc
            pos_data['lat'] = lat
            pos_data['lon'] = lon
            pos_data['battery'] = -1
            pos_data['accuracy'] = -1
            pos_data['date'] = date_data
            pos_data['altitude'] = alt
            pos_data['speed'] = 0
            pos_data['source'] = 'hist'

            database.insert_location(pos_data)
            # try:
            #     database.insert_location(pos_data)
            # except Exception as e:
            #     print("DB error: ", e)

    # 
    # random.shuffle(urls)
    # num_urls = len(urls)
    # for i, u in enumerate(urls):
    #     data = re.match('.*utc=(.*)&lat=(.*)&lon=(.*?)&.*&altitude=(.*)', u)
        # if data:
        #     print(f"{i}/{num_urls}", data.groups())
        #     utc = int(data.group(1))
        #     lat = float(data.group(2))
        #     lon = float(data.group(3))
        #     alt = float(data.group(4))
        #https://owntracks.exploretheworld.tech/log?utc=1565931690&lat=38.94425386&lon=-77.45050834&battery=-1&accuracy=-1&dev_id=ben&source=hist&altitude=65.775390625


