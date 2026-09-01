
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
country_file = os.path.join(config_dir, 'countries.csv')
# World country boundaries, id'd by ISO alpha-3 code. Derived from
# https://github.com/datasets/geo-countries (Natural Earth-based), with
# large countries' coastlines simplified to cut file size, and a couple
# of ISO codes the source data leaves as "-99" (France, Norway) fixed up
# by name -- see the generation notes in CLAUDE.md.
world_country_json = os.path.join(config_dir, 'world-countries.geojson')

# Served at /app_properties for the GPSLogger phone app's "Default
# Profile -> From URL" import -- see CLAUDE.md.
gpslogger_properties_file = os.path.join(config_dir, 'gpslogger_default_profile.properties')

# Precomputed pairwise distance matrix (TSPLIB format, 3,100 US county
# seats -- excludes Alaska/Hawaii, see CLAUDE.md) used by
# compute_unvisited_routes.py as the primary (real, road-influenced)
# distance source for the suggested-loop feature. Source:
# https://www.math.uwaterloo.ca/tsp/county/index.html (Bill Cook's
# "Optimal Tour for Extra Milers" page).
usa3100_tsp_file = os.path.join(config_dir, 'usa3100_mixed.tsp')
# [[name, lat, lon], ...], 3,100 entries, in the exact same order as
# usa3100_tsp_file's matrix rows/columns (verified this order empirically
# via a physical-consistency check -- see CLAUDE.md). Extracted from
# https://www.math.uwaterloo.ca/tsp/county/usa3100_points.html (fetched
# 2026-09-01) -- that page has no machine-readable download of its own,
# so this is a one-time extraction of its embedded `var locations` array,
# not a re-derivable build artifact.
usa3100_locations_file = os.path.join(config_dir, 'usa3100_locations.json')

# FIPS-prefix set for "continental US" (lower 48 + DC): excludes Alaska
# (02), Hawaii (15), and the territories (72 PR, 78 VI, 66 Guam, 60
# American Samoa, 69 N. Mariana Islands). Shared by _initilization's
# continental map-bounds fit and compute_unvisited_routes.py's mainland
# scope, so "mainland" means the same thing everywhere in the app.
non_continental_fips_prefixes = ['02', '15', '72', '78', '66', '60', '69']

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

# Source: https://gist.github.com/rogerallen/1583593
us_state_to_abbrev = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "District of Columbia": "DC",
    "American Samoa": "AS",
    "Guam": "GU",
    "Northern Mariana Islands": "MP",
    "Puerto Rico": "PR",
    "United States Minor Outlying Islands": "UM",
    "U.S. Virgin Islands": "VI",
}
    
# invert the dictionary
abbrev_to_us_state = dict(map(reversed, us_state_to_abbrev.items()))