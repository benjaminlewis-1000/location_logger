#! /usr/bin/env python

import os
import gpxpy
import time
import shutil
from datetime import datetime, timedelta

import location_db
import config

database = location_db.locationDB(db_name=config.database_location, \
        fips_file = config.county_fips_file, \
        country_file=config.country_file)

source_folder = '/data/gdrive_data/unprocessed'
dest_folder = '/data/gdrive_data/processed/GPSLogger'

def read_process_gps(file):
    assert os.path.exists(file)


    gpx_file = open(file, 'r')

    gpx = gpxpy.parse(gpx_file)

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                data = {'la'}
                # print(f'Point at ({point.latitude},{point.longitude}) -> {point.elevation}')

                # print(dir(point))

                uid_dict = {}
                user_id = 'ben'
                if user_id in uid_dict.keys():
                    uuid = uid_dict[user_id]
                else:
                    uuid = database.get_user_id(user_id)
                    uid_dict[user_id] = uuid


                utc = time.mktime(point.time.timetuple())
                # print(point.latitude, point.longitude, point.speed)

                
                pos_data = {}
                pos_data['uuid'] = uuid
                pos_data['dev_id'] = user_id
                pos_data['utc'] = utc
                pos_data['lat'] = point.latitude
                pos_data['lon'] = point.longitude
                pos_data['battery'] = -1
                pos_data['accuracy'] = -1
                pos_data['date'] = point.time
                pos_data['altitude'] = point.elevation
                if pos_data['altitude'] is None:
                    pos_data['altitude'] = -100
                pos_data['speed'] = 0
                pos_data['source'] = 'hist'

                database.insert_location(pos_data)
                
                # print("Here")
                # exit()

no_fails = True
for root, dirs, files in os.walk(source_folder):
    print(files)
    for f in files:
        source_path = os.path.join(root, f)
        if not source_path.endswith('.gpx'):
            continue

        dest_path = os.path.join(dest_folder, f)

        try:
            read_process_gps(source_path)
            shutil.move(source_path, dest_path)
        except Exception as e:
            print(f"Failure! {source_path}, {e}")
            no_fails = False
