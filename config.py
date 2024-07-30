
import os
cf = '/project/config_files'
cf = 'config_files'
# cf = 'config_files'

database_location = '/data/location.sqlite'
# database_location = 'location2.sqlite'
# database_location = '/data/location2.sqlite'
# Counties from: https://eric.clst.org/tech/usgeojson/
detailed_county_json = os.path.join(cf, 'gz_counties_detailed.json')
medium_county_json = os.path.join(cf, 'gz_counties_medium.json')
basic_county_json = os.path.join(cf, 'gz_counties_basic.json')
# county_geojson = os.path.join(cf, 'geojson-counties-fips.json')

county_fips_file = os.path.join(cf, 'state_and_county_fips_master.csv')
