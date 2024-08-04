#! /usr/bin/env python

import os
import gpxpy
import config
import location_db
import geopandas as gpd
from shapely.geometry import Point

# # Load the json file with county coordinates
geoData = gpd.read_file(config.basic_county_json)
# Set up a hook to the location database
database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)
# database.unset_all_points()
# exit()

root_dir = '/project/Downloads/historical_gpx'

files = [
        ('boulder.gpx', 2015),
         ('pvu_abq1.gpx', 2014),
         ('boise_seattle.gpx', 2011),
         ('boseman_yellowstone.gpx', 2013),
         ('boston_p3.gpx', 2005),
         ('boston_p4.gpx', 2005),
         ('boulder.gpx', 2015),
         ('carlsbad.gpx', 2014),
         ('conference_nm.gpx', 2014),
         ('co_ward_camp.gpx', 2014),
         ('dallas2.gpx', 2005),
         ('dallas.gpx', 2005),
         ('lagrande_spokane.gpx', 2013),
         ('muir_woods.gpx', 2012),
         ('nauvoo.gpx', 2004),
         ('nm_camping.gpx', 2014),
         ('okc.gpx', 2005),
         ('ok_to_70.gpx', 2005),
         ('orlando_1.gpx', 2002),
         ('orlando_2.gpx', 2002),
         ('orlando_3.gpx', 2002),
         ('reno_sf.gpx', 2012),
         ('pvu_abq1.gpx', 2014),
         ('pvu_abq2.gpx', 2014),
         ('pvu_reno.gpx', 2012),
         ('pvu_lagrande.gpx', 2013),
         ('reno_sf.gpx', 2012),
         ('rexburg_provo.gpx', 2013),
         ('salt_plains.gpx', 2004),
         ('scout_reservation.gpx', 2003),
         ('sea_vancouver.gpx', 2011),
         ('spokane_boseman.gpx', 2013),
         ('stillater_hale.gpx', 2005),
         ('to_boston_p1.gpx', 2005),
         ('to_boston_p2.gpx', 2005),
         ('to_branson.gpx', 2004),
         ('trip_to_park_ca.gpx', 2012),
         ('tuscon.gpx', 2014),
        ('to_chicago_2016.gpx', 2016),
        ('to_palmyra.gpx', 2017),
        ('raleigh_1.gpx', 2017),
        ('raleigh_2.gpx', 2017),
        ('raleigh_4.gpx', 2017),
        ('raleigh_3.gpx', 2017),
        ('nick_trip.gpx', 2014),
        ]

last_county = None
print(database.get_num_counties_visited())

for ff in files:
    fname = os.path.join(root_dir, ff[0])
    print(fname)
    year = ff[1]
    with open(fname, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)
    points = gpx.tracks[0].segments[0].points
    for point in points:
        lat = point.latitude
        lon = point.longitude
        qpt = Point(map(float, (lon, lat)))

        if last_county is None:
            last_county = geoData[geoData['geometry'].contains(qpt)]
            print(last_county)

            new_county_pair = (str(last_county['GEO_ID'].item()), year)
            database.set_visited_county(new_county_pair)

        # Now we have a last county that's consistent
        in_same_county = last_county['geometry'].contains(qpt)
        if not in_same_county.item(): 
            update_county = geoData[geoData['geometry'].contains(qpt)]
            if len(update_county) == 0:
                continue # Probably over water or something.
            print(update_county)
            new_county_pair = (str(update_county['GEO_ID'].item()), year)
            database.set_visited_county(new_county_pair)
            last_county = update_county

county_fips_list = [
    ('04013', 2014),
    ('49049', 2024),
    ('49035', 2000),
    ('32017', 2015),
    ]

for fip_pair in county_fips_list:
    database.set_visited_county(fip_pair)

# unset_fips_list = [
# # '45051', '45067', '45033', '45041','45031', '45069', \
# # '37153', '37123', '37151', '37081', '37067', '37189', '37171'\
# # 39141, 39079, 39053, 54053, 54079, 54019, 54081, 54055, 51021, 51197, 51035
# 54039,  37169
# ]

# for fips in unset_fips_list:
#     if type(fips) != str:
#         fips = str(fips)
#     database.unset_county_by_fips(fips)