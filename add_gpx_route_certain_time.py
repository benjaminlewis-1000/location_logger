#! /usr/bin/env python

import numpy as np
import gpxpy
from datetime import datetime, timedelta
from sqlalchemy.sql import select
from sqlalchemy import and_
import os
import add_vals_quick
from geopy.distance import geodesic as GD

files = [
    # ('part1.gpx', '2024-04-13 19:32:10', 2),
    # ('part2.gpx', '2024-04-13 23:04:20', 2.5),
    # ('part3.gpx', '2024-04-14 15:25:50', 2.4),
    # ('part4.gpx', '2024-04-14 20:05:50', 0.25),
    # ('part5.gpx', '2024-04-14 21:30:05', 6.5),
    # ('part6.gpx', '2024-04-19 23:41:49', 1.5),
    # ('part7.gpx', '2024-04-21 14:15:49', 2.2),
    # ('part8.gpx', '2024-04-21 18:01:09', 5.2),
    # ('part9.gpx', '2024-04-21 23:54:09', 4.7),
    # ('part10.gpx', '2024-04-13 12:59:44', 2.27), # End 2024-04-13 15:15:45
]


class GPXAdder(object):
    """docstring for GPXAdder"""
    def __init__(self, filelist):
        super(GPXAdder, self).__init__()
        self.filelist = filelist

        self.dist_thresh = 100
        self.user_id = 'ben'
        self.uuid = add_vals_quick.get_user_id(self.user_id)

        for file_tuple in filelist:
            file = os.path.join("Downloads", file_tuple[0])
            start_time = file_tuple[1]
            duration = file_tuple[2]
            self.process_data(file, start_time, duration)


    def datetime_to_utc(self, dt: datetime):
        return dt.timestamp()

    def datestring_to_datetime(self, datestring: str):
        dt = datetime.strptime(datestring, "%Y-%m-%d %H:%M:%S")
        return dt

    def utc_to_datetime(self, utc: float):
        dt_object = datetime.fromtimestamp(utc)
        return dt_object

    def process_data(self, file: str, start_time: str, duration: float):
        duration_sec = duration * 3600
        start_dt = self.datestring_to_datetime(start_time)
        start_utc = self.datetime_to_utc(start_dt)

        gpx_file = open(file, 'r')
        gpx = gpxpy.parse(gpx_file)
        points = gpx.tracks[0].segments[0].points

        duration_delta = timedelta(seconds=duration_sec)
        end_dt = start_dt + duration_delta
        end_utc = self.datetime_to_utc(end_dt)

        # Clear out the database

        conn = add_vals_quick.conn
        positions = add_vals_quick.positions

        # Clear out data in the time range
        query = and_(positions.c.utc_time > start_utc, positions.c.utc_time < end_utc)
        d = positions.delete().where(query)
        conn.execute(d)

        s = select([positions]).where(query)
        results = conn.execute(s)
        num_results = len(results.fetchall())
        print(f"There are {num_results} remaining records, {len(points)} points")
        # exit()

        distances = []
        for pp in range(len(points) - 1):
            if pp % 1000 == 0:
                print(pp)
            p1 = points[pp]
            p1 = (p1.latitude, p1.longitude)
            p2 = points[pp + 1]
            p2 = (p2.latitude, p2.longitude)
            dist = GD(p1, p2).m
            distances.append(dist)

        sum_distance = np.sum(distances)
        speed = sum_distance / duration_sec

        delta_dist = 0
        total_dist = 0
        elapsed_time = 0
        count = 0
        for dd in range(len(distances) ):
            delta_dist += distances[dd]
            total_dist += distances[dd]
            if delta_dist > self.dist_thresh:
                # Put the point in
                chosen_point = points[dd + 1]
                # print(start_utc, total_dist, speed)
                new_time = round(start_utc + total_dist / speed, 1)
                self.point_to_db(chosen_point, new_time)
                # print(f"Insert point {dd + 1}, {delta_dist}, {new_time}, {total_dist}")
                delta_dist = 0
                count += 1
        print(f"{count} points added.")

    def point_to_db(self, point, utc_time: float):

        utc_dt = self.utc_to_datetime(utc_time)

        pos_data = {}
        pos_data['uuid'] = self.uuid
        pos_data['dev_id'] = self.user_id
        pos_data['utc'] = utc_time
        pos_data['lat'] = point.latitude
        pos_data['lon'] = point.longitude
        pos_data['battery'] = -1
        pos_data['accuracy'] = -1
        pos_data['date'] = utc_dt
        pos_data['altitude'] = -999
        pos_data['speed'] = 0
        pos_data['source'] = 'hist'

        add_vals_quick.add_to_db(pos_data)
        

ff = GPXAdder(files)

exit()
        

# file = 'Downloads/part6.gpx'

# num_points = len(points)

# start_time = "2024-04-19 23:41:49"
# duration_sec = 3600 * 1.5
# duration_delta = timedelta(seconds=duration_sec)
# end_time = start_utc + duration_delta

# start_utc = start_utc.timestamp()
# end_utc = end_time.timestamp()

# delta_time = num_points / duration_sec

# conn = add_vals_quick.conn
# positions = add_vals_quick.positions

# # Clear out data in the time range
# query = and_(positions.c.utc_time > start_utc, positions.c.utc_time < end_utc)
# d = positions.delete().where(query)
# conn.execute(d)

# s = select([positions]).where(query)
# results = conn.execute(s)
# num_results = len(results.fetchall())
# print(f"There are {num_results} remaining records, {num_points} points")

# for jj in range(0, num_points, 15):

#     utc_time = int(jj * delta_time + start_utc)

    
