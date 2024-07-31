# Using graph_objects

from flask import Flask, render_template, Response
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
import geopandas as gpd
import re
import location_db
from flask_classful import FlaskView, route

app = Flask(__name__)

class FlaskApp(FlaskView):

    def __init__(self):
        super(FlaskApp, self).__init__()
        

        with open(config.basic_county_json, 'rb') as geodata:
            self.counties = json.load(geodata)

        # Edit GEO_ID field to remove the leading values
        for cc in range(len(self.counties['features'])):
            self.counties['features'][cc]['properties']['GEO_ID'] = re.sub(r'0500000US', '', self.counties['features'][cc]['properties']['GEO_ID'])

        self.database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)

        self.template = None
        self._precompute_graph()


    def _precompute_graph(self):

        ts = self.database.get_county_visits_dataframe()

        fig = px.choropleth(ts, geojson=self.counties, locations="FIPS", color='year',
                                   color_continuous_scale="Viridis",
                                   # range_color=(dmin, dmax),
                                   scope="usa"
                                  )

        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)   

        self.template = graphJSON

    @route('/counties')
    def county_idx(self):
    # http://localhost:5000/
        while self.template is None:
            time.sleep(0.25)
        return render_template('notdash.html', graphJSON=self.template)
        # return "<h1>This is my indexpage2</h1>"

FlaskApp.register(app,route_base = '/')        

# class FlaskApp(object):
#     """docstring for FlaskApp"""

#     app = None 

#     def __init__(self):
#         super(FlaskApp, self).__init__()
        

#         with open(config.basic_county_json, 'rb') as geodata:
#             self.counties = json.load(geodata)

#         # Edit GEO_ID field to remove the leading values
#         for cc in range(len(self.counties['features'])):
#             self.counties['features'][cc]['properties']['GEO_ID'] = re.sub(r'0500000US', '', self.counties['features'][cc]['properties']['GEO_ID'])

#         self.app = Flask(__name__)
#         self.add_endpoint(endpoint='/', handler=self.notdash, endpoint_name='county')
#         self.app.run(debug=True, port=8080, host='0.0.0.0')
#         self.template = None
#         self.precompute_graph()

    # def add_endpoint(self, endpoint=None, endpoint_name=None, handler=None):
    #         self.app.add_url_rule(endpoint, endpoint_name, EndpointAction(handler))



    # @self.app.route('/')
    # def notdash(self):


if __name__ == '__main__':
    app.run(debug=True, port=8080, host='0.0.0.0')
#     app = FlaskApp()
    

# fig.show()

# fig = go.Figure([go.Scatter(x=df['Date'], y=df['AAPL.High'])])
# fig.show()