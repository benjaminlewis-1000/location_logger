
import os

this_dir = os.path.dirname(os.path.realpath(__file__))
config_dir = os.path.join(this_dir, 'config_files')

database_location = '/data/location.sqlite'
database_location = 'location2.sqlite'
# database_location = '/data/location2.sqlite'
# Counties from: https://eric.clst.org/tech/usgeojson/
detailed_county_json = os.path.join(config_dir, 'gz_counties_detailed.json')
medium_county_json = os.path.join(config_dir, 'gz_counties_medium.json')
basic_county_json = os.path.join(config_dir, 'gz_counties_basic.json')
state_json = os.path.join(config_dir, 'us-states.json')

county_fips_file = os.path.join(config_dir, 'state_and_county_fips_master.csv')
