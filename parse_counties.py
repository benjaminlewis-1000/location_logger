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

# # Load the json file with county coordinates
geoData = gpd.read_file(config.basic_county_json)
# Set up a hook to the location database
database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)

# Get all the data in the table. Since I can't find a 
# performant SQL query that will find the row with the 
# minimum UTC time difference, I'll do it with 
# fetching all the data once and using numpy. 
database.unset_all_points()
alldata = database.retrieve_all_data()

# Get points where county_proc is null or False.
unprocessed_data = alldata[alldata.county_proc.isnull() | alldata.county_proc == False]
print(f"There are {len(unprocessed_data)} unprocessed points.")
# data = unprocessed_data[:10000]

# This is used to find the previous point sequentially in the
# database. 
utc_index = alldata.utc.to_numpy()

# Keep track of points that we've already processed into
# the database. 
county_ids = set()
last_county = None
last_point_year = None

for didx in tqdm(range(0, len(unprocessed_data))):

    # Get relevant data from the row
    id0, date0, utc0, lat0, lon0, _ = unprocessed_data.iloc[didx]
    # Find the closest index. 
    # Diff between this point's time and every other
    # time point in the database
    utc_diffs = utc0 - utc_index
    # Find points where the difference is positive (i.e. 
    # the point in question happened after these points).
    # Has to be >0, since 0 will be this point. 
    utc_eligible = np.array(np.where(utc_diffs > 0)[0])
    # For the very first temporal point in the database,
    # we don't have any previous points, so we'll just throw
    # it out and assume it doesn't represent a substantially
    # different location than other items in the DB. 
    if len(utc_eligible) == 0:
        database.set_point_county_processed(id0)
        continue

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
    id1, date1, utc1, lat1, lon1, _ = closest_time_data
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
    if speed < 45: 
    # 45 m/s ~= 100 mph. Faster than that is a plane, and I don't want to do those. 

        # Because the point is lon/lat for geodata instead
        # of lat/lon for geopy.distance, we reverse it. 
        qpt = Point(map(float, considered_coord[::-1]))

        # Set a baseline for last_county.
        if last_county is None:
            in_county = geoData[geoData['geometry'].contains(qpt)]
            assert len(in_county) == 1

            # Doesn't have a value
            if len(in_county) == 0: # Not in a US county:
                database.set_point_county_processed(id0)
                continue
            last_county = in_county
            last_point_year = date0.year
            print("New county! ", in_county['NAME'],  in_county['STATE'])
            new_county_pair = (str(last_county['GEO_ID'].item()), last_point_year)
            database.set_visited_county(new_county_pair)

        # Normal processing relative to last_county
        in_county = last_county['geometry'].contains(qpt)
        this_year = date0.year
        if in_county.item() and this_year == last_point_year:
            database.set_point_county_processed(id0)
        else:
            # Figure out if it's a new year or a new county
            if in_county.item():
                # Then not the same year
                assert this_year != last_point_year
                new_county_pair = (str(last_county['GEO_ID'].item()), this_year)
                # print("GEOID", last_county)
                last_point_year = this_year
                database.set_visited_county(new_county_pair)
                database.set_point_county_processed(id0)
            else:
                # Figure out the new county 
                new_county = geoData[geoData['geometry'].contains(qpt)]
                assert len(new_county) == 1
                # print("NC\n", new_county)
                # print("Name_id", new_county['NAME'], new_county['GEO_ID'])
                new_county_pair = (str(new_county['GEO_ID'].item()), this_year)
                database.set_visited_county(new_county_pair)
                database.set_point_county_processed(id0)

                last_point_year = this_year
                last_county = new_county
                print("New county! ", new_county['NAME'],  new_county['STATE'])

    else:
        # This point was too fast. 
        database.set_point_county_processed(id0)

print(database.get_num_visited(), 'counties visited')