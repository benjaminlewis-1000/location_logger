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
import county_db
import sqlalchemy
import numpy as np
# from sqlalchemy.engine.reflection import Inspector

# county_db_instance = county_db.countyDB(db_name = 'county.sqlite', fips_file = 'state_and_county_fips_master.csv')

# # Load the json file with county coordinates
# geoData = gpd.read_file(
#         # 'gz_2010_us_050_00_20m.json', encoding='latin1'
#         'gz_2010_us_050_00_500k.json', encoding='latin1'
# )
#     # 'https://raw.githubusercontent.com/holtzy/The-Python-Graph-Gallery/master/static/data/US-counties.geojson'

# geoData['geometry'].plot()
# p1 = Point(map(float, (-97.05, 36.11))) #  Stillwater, OK
# # print(geoData[geoData['geometry'].contains(p1)]) # That's the line for the appropriate county. 
# # plt.show()
# # exit()


engine = create_engine('sqlite:////home/benjamin/location_track/location.sqlite', echo=False)
insp = sqlalchemy.inspect(engine)
conn = engine.connect()

# Check that the table has a 'county_computed' field
assert set(insp.get_table_names()) == set(['users', 'positions'])
columns = insp.get_columns('positions')
cnames = [c['name'] for c in columns]
if 'county_processed' not in cnames:
    print("Newcol")
    engine.execute('alter table positions add column county_processed Boolean default False')
# exit()

metadata = MetaData()
users = Table('users', metadata,
        Column('id', Integer, primary_key=True),
        Column('dev_id', String),
    )

positions = Table('positions', metadata,
        Column('id', Integer, primary_key=True),
        Column('date', DateTime),
        Column('utc_time', Float, index=True),
        Column('user_id', None, ForeignKey('users.id')),
        Column('latitude', Float),
        Column('longitude', Float),
        Column('altitude', Float),
        Column('battery', Integer),
        Column('accuracy', Float),
        Column('speed', Float),
        Column('source', String),
        Column('county_processed', Boolean),
    )

# exit()

'''
WITH TargetRow AS (
    SELECT utc_time AS target_value
    FROM positions
    WHERE id = 7
)
SELECT nt.*, nt.utc_time - tr.target_value AS diff
FROM positions nt 
CROSS JOIN TargetRow tr
WHERE nt.id != 4 and diff > 0
ORDER BY diff ASC
LIMIT 1;
'''

print('p1')
# position_q = select(positions.c).where(positions.c.county_processed == False).order_by(positions.c.utc_time)
# pos_res = conn.execute(position_q)
# data = pos_res.fetchall()
# print('p2')

# Get all the data in the table. Since I can't find a 
# performant SQL query that will find the row with the 
# minimum UTC time difference, I'll do it with 
# fetching all the data once and using numpy. 
pc = positions.c
alldata_q = select([pc.id, pc.county_processed, pc.latitude, pc.longitude, pc.utc_time])
alldata = conn.execute(alldata_q)
alldata = alldata.fetchall()
alldata = pd.DataFrame(alldata)

unprocessed_data = alldata[alldata.county_processed == False]
print(f"There are {len(unprocessed_data)} points.")
data = unprocessed_data[:100]

utc_index = alldata.utc_time.to_numpy()

print(data[0])
# exit()


# for didx in range(len(data) - 1):
county_ids = set()
state_ids = set()
last_county = None

pid0, _, lat0, lon0, utc0 = data[0]
qpt = Point(map(float, (lon0, lat0)))
county = geoData[geoData['geometry'].contains(qpt)]
idx = 1
while len(county) == 0:
    pid0, _, lat0, lon0, utc0 = data[idx]
    qpt = Point(map(float, (lon0, lat0)))
    county = geoData[geoData['geometry'].contains(qpt)]
    idx += 1

last_county = county
county_ids.add(county['GEO_ID'].item())
state_ids.add(county['STATE'].item())

for didx in tqdm(range(idx, len(data) - 1)):
    pid0, _, lat0, lon0, utc0 = data.iloc[didx]
    # Find the closest index. 
    utc_diffs = utc0 - utc_index
    utc_eligible = np.where(utc_diffs > 0)
    eligible_idx = np.argmin(utc_diffs[utc_eligible])
    closest_time_diff = int(utc_diffs[utc_eligible][eligible_idx])
    closest_time_idx = int(utc_eligible[0][eligible_idx])
    closest_time_data = alldata.iloc[closest_time_idx]

    pid1, _, lat1, lon1, utc1 = closest_time_data
    coord1 = (lat0, lon0) # data[didx][1], data[didx][2])
    coord2 = (lat1, lon1) # data[didx + 1][1], data[didx + 1][2])
    dist = geopy.distance.geodesic(coord1, coord2).m
    # print(dist)
    time = utc0 - utc1 # data[didx + 1][3] - data[didx][3]
    assert time > 0 
    if time > 0:
        speed = dist / time
        # print(speed, "m/s")
        if speed < 65:
            pass
            qpt = Point(map(float, (lon1, lat1)))
            if last_county is not None:
                in_county = last_county['geometry'].contains(qpt)
                if in_county.item():
                # print(in_county)
                    pass
                else:
                    county = geoData[geoData['geometry'].contains(qpt)]
                    if len(county) > 0:
                        assert len(county) == 1
                        last_county = county
                        print(f"New county! {county['NAME'].item()}")
                        county_ids.add(county['GEO_ID'].item())
                        state_ids.add(county['STATE'].item())
        # Then you can look up the county.
    assert time >= 0

    