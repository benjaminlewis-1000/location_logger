
import os
cf = '/project/config_files'
# cf = 'config_files'

# database_location = '/data/location.sqlite'
database_location = 'location2.sqlite'
detailed_county_json = os.path.join(cf, 'gz_counties_detailed.json')
medium_county_json = os.path.join(cf, 'gz_counties_medium.json')
basic_county_json = os.path.join(cf, 'gz_counties_basic.json')

county_fips_file = os.path.join(cf, 'state_and_county_fips_master.csv')
