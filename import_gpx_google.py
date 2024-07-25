#! /usr/bin/env python

import os
import gpxpy
import add_vals_quick
import time
import shutil
from datetime import datetime, timedelta

source_folder = '/data/gdrive_data/unprocessed'
dest_folder = '/data/gdrive_data/processed'

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
                    uuid = add_vals_quick.get_user_id(user_id)
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

                add_vals_quick.add_to_db(pos_data)


for root, dirs, _ in os.walk(source_folder):
    for d in dirs:
        d_files = os.listdir(os.path.join(root, d))
        gpx_files = [f for f in d_files if f.endswith('.gpx')]
        # print(d, gpx_files)
        no_fails = True
        print(d)
        os.makedirs(os.path.join(dest_folder, d), exist_ok=True)
        for gg in gpx_files:
            source_path = os.path.join(root, d, gg)
            dest_path = os.path.join(dest_folder, d, gg)
            # read_process_gps(os.path.join(root, d, gg))
            print(source_path)

            try:
                read_process_gps(source_path)
                shutil.move(source_path, dest_path)
            except Exception as e:
                print(f"Failure! {source_path}, {e}")
                no_fails = False


        if no_fails and d != 'holding_dir':
            shutil.rmtree(os.path.join(root, d))
