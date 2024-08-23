#! /usr/bin/env python

import plotly.express as px
import location_db
import config

db_location = 'loc.bak'
database = location_db.locationDB(db_name = db_location,\
                    fips_file = config.county_fips_file, \
                    country_file=config.country_file)

county_df = database.get_county_visits_dataframe()

fig = px.choropleth(county_df, geojson=self.counties, locations="FIPS", color='year',
                           color_continuous_scale=self.colorscale_county,
                           # range_color=(dmin, dmax),
                           scope="usa"
                          )
fig = self.__set_map_layout(fig)