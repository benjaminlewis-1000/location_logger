
import os
import numpy as np

this_dir = os.path.dirname(os.path.realpath(__file__))
config_dir = os.path.join(this_dir, 'config_files')

database_location = '/data/location.sqlite'
# database_location = 'location.sqlite'
# database_location = '/data/location2.sqlite'
# Counties from: https://eric.clst.org/tech/usgeojson/
detailed_county_json = os.path.join(config_dir, 'gz_counties_detailed.json')
medium_county_json = os.path.join(config_dir, 'gz_counties_medium.json')
basic_county_json = os.path.join(config_dir, 'gz_counties_basic.json')
# state_json = os.path.join(config_dir, 'us-states.json')

county_fips_file = os.path.join(config_dir, 'state_and_county_fips_master.csv')

# These won't capture the entire county, but are designed
# to get the bulk of the points from the county.
# Doesn't have to be all of a county, it can just be a 
# designated area. Should be contained in a county, though.
frequent_counties = [
    {"Name": "Greene",
     "State": "OH",
     "LeftLon": -84.09,
     "TopLat": 39.825,
     "RightLon": -83.87,
     "BotLat": 39.57},
    {"Name": "Clark",
     "State": "OH",
     "LeftLon": -84.03,
     "TopLat": 40.00,
     "RightLon": -83.87,
     "BotLat": 39.57},
    {"Name": "Montgomery", # Verified
     "State": "OH",
     "LeftLon": -84.47,
     "TopLat": 39.88,
     "RightLon": -84.11, 
     "BotLat": 39.59},
    {"Name": "Warren",
     "State": "OH",
     "LeftLon": -84.33,
     "TopLat": 39.56,
     "RightLon": -84, 
     "BotLat": 39.29},
    {"Name": "Utah",
     "State": "UT",
     "LeftLon": -112.04,
     "TopLat": 40.40,
     "RightLon": -111.58, 
     "BotLat": 39.95},
    {"Name": "Salt Lake",
     "State": "UT",
     "LeftLon": -112.15,
     "TopLat": 40.81,
     "RightLon": -111.80, 
     "BotLat": 40.49},
]

# These are not counties, but are areas/borders that are frequented enough.
frequent_areas = [
    {"Name": "AreaB", # Not exact, but I'm positive I go to Montgomery frequently enough.
     "State": "OH",
     "LeftLon": -84.10,
     "TopLat": 39.80,
     "RightLon": -84.02,
     "BotLat": 39.78},
    {"Name": "AreaA", 
     "State": "OH",
     "LeftLon": -84.19,
     "TopLat": 39.795,
     "RightLon": -84.07,
     "BotLat": 39.77},
    {"Name": "Green County Line", # Not exact, but again, positive that I'll be in both counties.
     "State": "OH",
     "LeftLon": -84.11,
     "TopLat": 39.78,
     "RightLon": -84.09, 
     "BotLat": 39.59 }
     ]

frequent_counties += frequent_areas

for ff in frequent_counties:
    expected = set(['Name', 'State', 'LeftLon', 'TopLat', 'RightLon', 'BotLat'])
    assert expected - set(ff.keys()) == set()
    assert ff['LeftLon'] < ff['RightLon']
    assert ff['BotLat'] < ff['TopLat']
    # Check the areas for sanity
    assert np.abs(ff['LeftLon'] - ff['RightLon']) < 1
    assert np.abs(ff['BotLat'] - ff['TopLat']) < 1