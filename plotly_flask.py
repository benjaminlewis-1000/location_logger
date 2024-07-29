# Using graph_objects

from flask import Flask, render_template
import pandas as pd
import json
import plotly
import plotly.express as px
from urllib.request import urlopen
import json
import requests
import os
import pandas as pd
import plotly.express as px
import numpy as np
from plotly import utils
from json import dumps
import time
import config
import geojson
import geopandas as gpd
import re

app = Flask(__name__)

@app.route('/')
def notdash():


    s = time.time()
    with urlopen('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json') as response:
        cc = json.load(response)
        print(cc)
    # Load the json file with county coordinates
    counties = gpd.read_file(config.basic_county_json, encoding='latin1')
    ID_FIELD="GEO_ID"
    counties[ID_FIELD] = [re.sub(r'0500000US', '', str(x)) for x in counties[ID_FIELD]]
    print(counties)
    print(time.time() - s)

    tsfile = 'time_series_covid19_confirmed_US.csv'
    tsurl = 'https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/' + tsfile

    if not os.path.exists(tsfile):
        req = requests.get(tsurl)
        with open(tsfile, 'wb') as f:
            f.write(req.content)
    ts = pd.read_csv(tsfile)
    print(time.time() - s)

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
    print(time.time() - s)
    print(ts_short)


    fig = px.choropleth(ts_short, geojson=counties, locations="FIPS", color='5/10/20',
                               color_continuous_scale="Viridis",
                               range_color=(dmin, dmax),
                               scope="usa"
                              )

    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    print(time.time() - s)


    # df = pd.DataFrame({
    #   'Fruit': ['Apples', 'Oranges', 'Bananas', 'Apples', 'Oranges', 
    #   'Bananas'],
    #   'Amount': [4, 1, 2, 2, 4, 5],
    #   'City': ['SF', 'SF', 'SF', 'Montreal', 'Montreal', 'Montreal']
    # })   
    # fig = px.bar(df, x='Fruit', y='Amount', color='City', 
    #   barmode='group')   
    # graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)   
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)   
    print(time.time() - s)
    return render_template('notdash.html', graphJSON=graphJSON)

if __name__ == '__main__':
    app.run(debug=True, port=8080, host='0.0.0.0')

# fig.show()

# fig = go.Figure([go.Scatter(x=df['Date'], y=df['AAPL.High'])])
# fig.show()