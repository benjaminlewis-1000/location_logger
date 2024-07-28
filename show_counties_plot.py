

# Trying to render the USA counties map with simple numeric data. This code fails to render several states:

from urllib.request import urlopen
import json
import requests
import os
import pandas as pd
import plotly.express as px
import geopandas as gpd
# import geoplot.crs as gcrs
# import geoplot as gplt
# import matplotlib.pyplot as plt
# from shapely.geometry import Point
# from tqdm import tqdm

# Load the json file with county coordinates
geoData = gpd.read_file(
        'gz_2010_us_050_00_20m.json', encoding='latin1'
)

# with urlopen('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json') as response:
#     counties = json.load(response)

# counties = json.load('gz_2010_us_050_00_5m.json')

# tsfile = 'time_series_covid19_confirmed_US.csv'
# tsurl = 'https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/' + tsfile

# if not os.path.exists(tsfile):
#     req = requests.get(tsurl)
#     with open(tsfile, 'wb') as f:
#         f.write(req.content)
# ts = pd.read_csv(tsfile)

# ts.dropna(inplace=True)
# ts = ts[ts['FIPS'] < 80000].copy(deep=True)

# ts_short = ts[['FIPS', '5/9/20', '5/10/20']].copy(deep=True)
# ts_short['delta'] = ts_short['5/10/20'] - ts_short['5/9/20']
# ts_short = ts_short[ts_short['delta'] >= 0].copy(deep=True)
# dmin = ts_short['5/10/20'].min()
# dmax = ts_short['5/10/20'].max()

fig = px.choropleth(geoData, locations='STATE', 
                           scope="usa"
                          )

fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

fig.show()
