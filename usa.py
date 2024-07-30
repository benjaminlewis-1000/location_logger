from urllib.request import urlopen
import json
import requests
import os
import pandas as pd
import plotly.express as px
import numpy as np
from plotly import utils
from json import dumps
import config

import geopandas as gpd
# counties = gpd.read_file(config.basic_county_json, encoding='latin1').to_geo_dict()

# d = gpd.read_file(config.basic_county_json, encoding='latin1')
# d2 = gpd.read_file(config.county_geojson, encoding='latin1')
# exit()
with open(config.basic_county_json, 'rb') as geodata:
    counties = json.load(geodata)

    # , encoding="ISO-8859-1")

# # with urlopen('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json') as response:
# with open(config.county_geojson, 'r') as geodata:
#     counties2 = json.load(geodata)



# print(counties['features'][0])
# print(counties2['features'][0])
# exit()

tsfile = 'time_series_covid19_confirmed_US.csv'
tsurl = 'https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/' + tsfile

if not os.path.exists(tsfile):
    req = requests.get(tsurl)
    with open(tsfile, 'wb') as f:
        f.write(req.content)
ts = pd.read_csv(tsfile)

ts.dropna(inplace=True)
ts = ts[ts['FIPS'] < 80000].copy(deep=True)

ts_short = ts[['FIPS', '5/9/20', '5/10/20']].copy(deep=True)
ts_short['delta'] = np.abs(ts_short['5/10/20'] - ts_short['5/9/20'])
ts_short = ts_short[ts_short['delta'] >= 0].copy(deep=True)
dmin = ts_short['5/10/20'].min()
dmax = ts_short['5/10/20'].max()
ts_short.FIPS = ts_short.FIPS.apply(int)
ts_short.FIPS = ts_short.FIPS.apply(str)
ts_short['FIPS'] = ts_short['FIPS'].str.zfill(5)


fig = px.choropleth(ts_short, geojson=counties, locations='FIPS', color='5/10/20',
                           color_continuous_scale="Viridis",
                           range_color=(dmin, dmax),
                           scope="usa"
                          )

fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

fig.show()

# import plotly.figure_factory as pff
# fig2 = pff.create_choropleth(fips=ts_short['FIPS'], values=ts_short['5/10/20'])
# fig2.show()
# import plotly.figure_factory as ff

# fips = ['06021', '06023', '06027',
#         '06029', '06033', '06059',
#         '06047', '06049', '06051',
#         '06055', '06061']
# values = range(len(fips))

# # fig = ff.create_choropleth(fips=fips, geojson=counties, values=values)
# fig.layout.template = None
# fig.show()