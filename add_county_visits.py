#! /usr/bin/env python

import os
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float, create_engine, Boolean
from sqlalchemy.sql import select
import geopy.distance

import geopandas as gpd
import geoplot.crs as gcrs
import geoplot as gplt
import matplotlib.pyplot as plt
from shapely.geometry import Point
from tqdm import tqdm
import pandas as pd
import location_db
import sqlalchemy
import numpy as np
import config

class CountyAdder(object):
    """docstring for CountyAdder"""
    def __init__(self):
        super(CountyAdder, self).__init__()

        # Load the json file with county coordinates
        self.geoData = gpd.read_file(config.basic_county_json)
        # Set up a hook to the location database
        self.database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)

        self.speed_thresh = 45 # 45 m/s ~= 100 mph

    def reset_db(self):
        self.database.unset_all_points()

    def iterate_until_done(self):
        num_left = 99999
        # Get the number left to process
        while num_left > 100:
            num_left = self.database.count_unprocessed_counties()
            self.process_points(num_points = 50000)

    def process_points(self, num_points = None):
        # Get all the data in the table. Since I can't find a 
        # performant SQL query that will find the row with the 
        # minimum UTC time difference, I'll do it with 
        # fetching all the data once and using numpy. 

        # self.alldata = self.database.get_points_to_parse_dataframe(start_utc = 1718682342, num_points=num_points)
        # self.alldata = self.database.get_points_to_parse_dataframe(start_utc = 1722543816, num_points=num_points)
        self.alldata = self.database.get_points_to_parse_dataframe(num_points=num_points)
        self.utc_index = self.alldata.utc.to_numpy()

        if self.alldata is None:
            exit()

        self.alldata['simple_speed'] = 999.0
        self.alldata['averaged_speed'] = 999.0

        # self.alldata = database.get_debug_subset()
        # self.alldata.county_proc = False
        # self.alldata.at[0, 'county_proc'] = True

        # Get points where county_proc is null or False.
        unprocessed_data = self.alldata[self.alldata.county_proc.isnull() | self.alldata.county_proc == False]

        infrequent_unprocessed, latest_in_frequent_counties = self.remove_frequent_counties(unprocessed_data)

        for ll in latest_in_frequent_counties:
            self.add_one_off_point(ll)

        # Calculate speeds
        self.calculate_speeds(infrequent_unprocessed)
        # Then filter based on speed
        too_fast = (infrequent_unprocessed.simple_speed > self.speed_thresh) \
            | (infrequent_unprocessed.averaged_speed > self.speed_thresh)
        good_speeds = ~too_fast
        filtered_points = infrequent_unprocessed[good_speeds].copy()

        # Find the ID's of the too fast points and set them to processed
        fast_ids = infrequent_unprocessed[too_fast].id.tolist()
        self.database.set_pointlist_county_processed(fast_ids)

        # Replay the counties.
        self.replay_counties(filtered_points)
        

    def add_one_off_point(self, point_df_entry):
        # This is for the latest_in_frequent_counties variables.

        lat = float(point_df_entry.lat)
        lon = float(point_df_entry.lon)
        year = point_df_entry.datetime.year
        id_num = int(point_df_entry.id)

        county_lookup = self._look_up_county(lat, lon)
        new_county_pair = (str(county_lookup['GEO_ID'].item()), year)
        self.database.set_visited_county(new_county_pair)
        # Set as processed regardless.
        self.database.set_point_county_processed(id_num)

    def _look_up_county(self, lat: float, lon: float):
        qpt = Point(map(float, (lon, lat)))

        in_county = self.geoData[self.geoData['geometry'].contains(qpt)]
        return in_county
    #     # Set a baseline for last_county.
    #     if last_county is None:

    def calculate_speeds(self, infrequent_array, n_away = 5):
        # Calculate speeds for the infrequent values. 
        # Used to remove counties that we go over in airplanes.

        avg_speed_col = infrequent_array.columns.get_loc('averaged_speed')
        inst_speed_col = infrequent_array.columns.get_loc('simple_speed')

        # for rownum in range(len(infrequent_array)):
        # tqdm(range(0, len(unprocessed_data)))
        for rownum in tqdm(range(len(infrequent_array) - 5)):
            row = infrequent_array.iloc[rownum]
            utc = float(row.utc)
            lat = float(row.lat)
            lon = float(row.lon)

            # Find n points before and after this point.
            utc_diffs = utc - self.utc_index
            # Find points where the difference is positive (i.e. 
            # the point in question happened after these points).
            # Has to be >0, since 0 will be this point. 
            utc_before = np.array(np.where(utc_diffs > 0)[0])
            utc_after = np.array(np.where(utc_diffs < 0)[0])

            before_vals = utc_diffs[utc_before]
            after_vals = utc_diffs[utc_after]

            before_sorted = np.argsort(before_vals)
            if len(before_sorted) == 0:
                n_before_data = row
                before_1_data = row
                n_before_rel_idx = 0
                before_1_rel_idx = 0
                n_before_absolute_idx = None
                before_1_absolute_idx = None
            else:
                n_before_rel_idx = int(before_sorted[:n_away][-1])
                n_before_absolute_idx = int(utc_before[n_before_rel_idx])
                n_before_data = self.alldata.iloc[n_before_absolute_idx]

                before_1_rel_idx = int(before_sorted[0])
                before_1_absolute_idx = int(utc_before[before_1_rel_idx])
                before_1_data = self.alldata.iloc[before_1_absolute_idx]
                    

            after_sorted = np.argsort(after_vals)
            n_after_rel_idx = int(after_sorted[-n_away:][0])
            n_after_absolute_idx = int(utc_after[n_after_rel_idx])
            n_after_data = self.alldata.iloc[n_after_absolute_idx]

            after_1_rel_idx = int(after_sorted[-1])
            after_1_absolute_idx = int(utc_after[after_1_rel_idx])
            after_1_data = self.alldata.iloc[after_1_absolute_idx]

            ############################
            # Calculate average speeds
            ############################
            before_position = (float(n_before_data.lat), float(n_before_data.lon))
            after_position = (float(n_after_data.lat), float(n_after_data.lon))

            before_time = float(n_before_data.utc)
            after_time = float(n_after_data.utc)
            # print(before_time, after_time, n_before_rel_idx)

            dist = geopy.distance.geodesic(before_position, after_position).m
            timediff = np.abs(after_time - before_time)
            speed = dist / timediff

            infrequent_array.iat[rownum, avg_speed_col] = speed
            
            ############################
            # Calculate instantaneous speeds
            ############################
            before_position_1 = (float(before_1_data.lat), float(before_1_data.lon))
            current_position = (float(row.lat), float(row.lon))
            after_position_1 = (float(after_1_data.lat), float(after_1_data.lon))

            before_time_1 = float(before_1_data.utc)
            current_time = float(row.utc)
            after_time_1 = float(after_1_data.utc)
            # print(before_time, after_time, n_before_rel_idx)

            dist_1 = geopy.distance.geodesic(before_position_1, current_position).m
            timediff_1 = np.abs(current_time - before_time_1)
            if timediff_1 == 0:
                print(timediff_1, before_time_1, after_time_1, before_1_absolute_idx, after_1_absolute_idx)
                speed_1 = 1000
            else:
                speed_1 = dist_1 / timediff_1

            infrequent_array.iat[rownum, inst_speed_col] = speed_1


        return infrequent_array.copy()
        
    def remove_frequent_counties(self, unprocessed_dataframe):
        # Use the squares that inscribe counties, as defined
        # in config.py, to remove points that we don't
        # want to process over and over again. We presume that 
        # most points will be in these counties, and it's not 
        # worth doing a GEOJSON lookup for all of them. 
        # Naturally, you could go and do something like this for
        # every county, but that would be a massive undertaking
        # and not worth it. This is to do a quick-and-dirty approach.
        latest_county_points = []
        for county in config.frequent_counties:

            if len(unprocessed_dataframe) == 0:
                # Nothing less to process on
                continue
            
            frequent_points = (unprocessed_dataframe['lon'] > county['LeftLon']) \
                    & (unprocessed_dataframe['lon'] < county['RightLon']) \
                    & (unprocessed_dataframe['lat'] < county['TopLat']) \
                    & (unprocessed_dataframe['lat'] > county['BotLat'])
            not_in_county = ~frequent_points

            # Get the latest value in this county so that it will be updated
            # in the database (e.g. update the year). 
            in_county = unprocessed_dataframe[frequent_points].copy()
            if len(in_county) == 0:
                # No points here. 
                continue
            latest_entry_idx = int(in_county['datetime'].argmax())
            latest_entry = in_county.iloc[latest_entry_idx]
            latest_county_points.append(latest_entry)
            # print('before',  len(in_county))
            # print(in_county.iloc[latest_entry_idx].name)
            in_county.drop(in_county.iloc[latest_entry_idx].name, inplace=True)
            # print('after', len(in_county))

            # TODO: Set these as processed.
            in_county_ids = in_county.id.tolist()
            self.database.set_pointlist_county_processed(in_county_ids)


            # Filter these points out.
            unprocessed_dataframe = unprocessed_dataframe[not_in_county].copy()

            
        return unprocessed_dataframe, latest_county_points

    def replay_counties(self, filtered_df):
        # Once the dataframe is filtered appropriately, go through
        # the remainder and decide county associations. 
        last_county = None

        for rownum in tqdm(range(len(filtered_df))):
            record = filtered_df.iloc[rownum]
            lat = record.lat
            lon = record.lon
            id0 = record.id
            date0 = record.datetime
            # Because the point is lon/lat for geodata instead
            # of lat/lon for geopy.distance, we reverse it. 
            qpt = Point(map(float, (lon, lat)))

            # Set a baseline for last_county.
            if last_county is None:
                in_county = self.geoData[self.geoData['geometry'].contains(qpt)]
                # assert len(in_county) == 1

                # Doesn't have a value
                if len(in_county) == 0: # Not in a US county:
                    self.database.set_point_county_processed(id0)
                    continue
                last_county = in_county
                last_point_year = date0.year
                print("New county! ", in_county, date0)
                new_county_pair = (str(last_county['GEO_ID'].item()), last_point_year)
                self.database.set_visited_county(new_county_pair)

            # Normal processing relative to last_county
            in_county = last_county['geometry'].contains(qpt)
            this_year = date0.year
            if in_county.item() and this_year == last_point_year:
                self.database.set_point_county_processed(id0)
            else:
                # Figure out if it's a new year or a new county
                if in_county.item():
                    # Then not the same year
                    assert this_year != last_point_year
                    new_county_pair = (str(last_county['GEO_ID'].item()), this_year)
                    # print("GEOID", last_county)
                    last_point_year = this_year
                    self.database.set_visited_county(new_county_pair)
                    self.database.set_point_county_processed(id0)
                else:
                    # Figure out the new county 
                    new_county = self.geoData[self.geoData['geometry'].contains(qpt)]
                    if len(new_county) == 0:
                      self.database.set_point_county_processed(id0)
                      continue

                    assert len(new_county) == 1
                    # print("NC\n", new_county)
                    # print("Name_id", new_county['NAME'], new_county['GEO_ID'])
                    new_county_pair = (str(new_county['GEO_ID'].item()), this_year)
                    self.database.set_visited_county(new_county_pair)
                    self.database.set_point_county_processed(id0)

                    last_point_year = this_year
                    last_county = new_county
                    print("New county! \n", new_county, "\n", date0)


if __name__ == "__main__":
    adder = CountyAdder()
    # @ # # adder.reset_db()
    # adder.process_points(num_points = 50000)
    adder.iterate_until_done()

'''
raise NotImplementedError("Need to preprend some processed data if it exists")
print(f"There are {len(unprocessed_data)} unprocessed points.")
# data = unprocessed_data[:10000]

# This is used to find the previous point sequentially in the
# database. 

# Keep track of points that we've already processed into
# the database. 
county_ids = set()
last_county = None
last_point_year = None

for didx in tqdm(range(0, len(unprocessed_data))):
# for didx in range(0, len(unprocessed_data)):

    # Get relevant data from the row
    id0, date0, utc0, lat0, lon0, _, _, _, _ = unprocessed_data.iloc[didx]
    # Find the closest index. 
    # Diff between this point's time and every other
    # time point in the database
    

    # Index back in to utc_diffs and find the minimum
    # value of the eligible differences. This will
    # give an index into utc_eligible, which we then 
    # have to index back out to absolute terms in utc_diffs. 
    eligible_idx = np.argmin(utc_diffs[utc_eligible])
    closest_time_diff = int(utc_diffs[utc_eligible][eligible_idx])
    # utc_eligible is indices in utc_diffs itself. 
    closest_time_idx = int(utc_eligible[eligible_idx])
    # Then get the appropriate row from alldata. 
    closest_time_data = alldata.iloc[closest_time_idx]

    # And pick that data from that row. Then compute
    # the distance between the points and the speed. 
    id1, date1, utc1, lat1, lon1, _, _, _, _ = closest_time_data
    considered_coord = (lat0, lon0) # data[didx][1], data[didx][2])
    coord2 = (lat1, lon1) # data[didx + 1][1], data[didx + 1][2])
    dist = geopy.distance.geodesic(considered_coord, coord2).m
    # print(dist)
    timediff = utc0 - utc1 # data[didx + 1][3] - data[didx][3]
    
    assert timediff >= 0 

    # Shouldn't happen, since we asked for utc_diffs > 0
    if timediff == 0:
        database.set_point_county_processed(id0)
        continue

    speed = dist / timediff
    unprocessed_data.at[didx, 'simple_speed']  = speed

    # speeds.pop(0)
    # speeds.append(speed)
    # mean_spd = np.mean(speeds)

    # # print(speed, mean_spd, timediff, dist, closest_time_idx)

print(database.get_num_counties_visited(), 'counties visited')
'''