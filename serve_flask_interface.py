# Using graph_objects

from datetime import datetime, timedelta, date
from dotenv import load_dotenv
from flask import Flask, render_template, Response, request
from flask_classful import FlaskView, route
from flask_cors import CORS, cross_origin
from flask_googlemaps import GoogleMaps, Map
from json import dumps
from plotly import utils
from urllib.request import urlopen
import config
import geopandas as gpd
import json
import jsonpickle
import location_db
import math
import numpy as np
import os
import pandas as pd
import plotly
import plotly.express as px
import re
import requests
import time

app = Flask(__name__)
load_dotenv()

cors = CORS(app, resources={r"/foo": {"origins": "*"}})
# SESSION_TYPE = 'redis'
app.config.from_object(__name__)
app.config['CORS_HEADERS'] = 'Content-Type'
gmap_key = os.environ['GMAP_API_KEY']
app.config['GOOGLEMAPS_KEY'] = gmap_key
app.config['UPLOAD_FOLDER'] = "/data"
GoogleMaps(app)

class FlaskApp(FlaskView):

    def __init__(self):
        super(FlaskApp, self).__init__()
        

        with open(config.basic_county_json, 'rb') as geodata:
            self.counties = json.load(geodata)

        # Edit GEO_ID field to remove the leading values
        for cc in range(len(self.counties['features'])):
            self.counties['features'][cc]['properties']['GEO_ID'] = re.sub(r'0500000US', '', self.counties['features'][cc]['properties']['GEO_ID'])

        self.database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)


        self.colorscale = plotly.colors.sequential.Viridis
        self.colorscale = self.colorscale[::-1]
        self.colorscale_county = self.colorscale.copy()
        self.colorscale_county[0] = '#ffeae8'

        self.template = None
        self.compute_running = False
        self.num_counties_visited = 0
        tmp = self.database.get_county_visits_dataframe()
        self.num_counties = len(tmp)
        self.max_county_year = self.database.get_average_visit_year()
        del tmp
        self._precompute_graph()

    def set_map_layout(self, fig):

        fig.update_layout(
                autosize=True,
                coloraxis_colorbar_len=0.7,
                coloraxis_colorbar_title='Year',
                margin = dict(
                        l=0,
                        r=0,
                        b=0,
                        t=0,
                        pad=4,
                        autoexpand=True
                    ),
                    width=1600,
                    height=800,
            )


        return fig

    def _precompute_graph(self):

        self.compute_running = True
        self.template = None

        county_df = self.database.get_county_visits_dataframe()
        self.max_county_year = self.database.get_average_visit_year()
        print("call")
        # print(county_df)
        self.num_counties_visited = int(county_df.visited.sum())


        fig = px.choropleth(county_df, geojson=self.counties, locations="FIPS", color='year',
                                   color_continuous_scale=self.colorscale_county,
                                   # range_color=(dmin, dmax),
                                   scope="usa"
                                  )
        fig = self.set_map_layout(fig)

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        self.template = graphJSON
        self.compute_running = False

    @route('/counties')
    def serve_county_graph(self):

        # Check whether the precomputed graph is up to date.
        num_visited = self.database.get_num_counties_visited()
        max_county_year = self.database.get_average_visit_year()
        avg_county_year 

        if not self.compute_running and (num_visited != self.num_counties_visited or max_county_year != self.max_county_year): # or self.template is None:
            # Kick it off again.
            print("Recomputing")
            self._precompute_graph()

        while self.template is None:
            time.sleep(0.25)

        visited_string = f' - {num_visited}/{self.num_counties} | {num_visited / self.num_counties * 100:.2f}%'

        return render_template('notdash.html', graphJSON=self.template, stat_string=visited_string, title='Visited Counties')
        # return "<h1>This is my indexpage2</h1>"

    @route('/states')
    def serve_state_graph(self):
        print("State")

        state_df = self.database.get_state_visits_dataframe()
        num_visited = len(state_df[state_df.visited == True])

        dc_visited = bool(state_df[state_df.state == 'DC'].visited.any())
        if dc_visited:
            num_visited -= 1
            
        visited = state_df[state_df.visited]
        visit_states = visited.state.tolist()
        visit_year = visited.year.tolist()

        fig = px.choropleth(locations=visit_states, locationmode="USA-states", 
                    color=visit_year,
                    color_continuous_scale=self.colorscale,
                    scope="usa")

        fig = self.set_map_layout(fig)
        visited_string = f' | {num_visited}/50 States{" & DC" if dc_visited else ""} Visited'

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        return render_template('notdash.html', graphJSON=graphJSON, stat_string=visited_string, title='Visited States')


    @route('/log', methods=['GET', 'POST'])
    # https://owntracks.exploretheworld.tech/log
    # HTTP body: %ALL
    # lat=%LAT&lon=%LON&timestamp=%TIMESTAMP&battery=%BATT&acc=%ACC&spd=%SPD
    def logger(self):

        data = request.data.decode('utf-8')
        data = data.split('&')
        vals = {a.split('=')[0]:a.split('=')[1] for a in data if a != ''}
        
        pos_data = {}
        cur_datetime = datetime.utcfromtimestamp(int(vals['timestamp']))
        pos_data['utc'] = vals['timestamp']
        pos_data['lat'] = vals['lat']
        pos_data['lon'] = vals['lon']
        pos_data['battery'] = vals['battery'] if 'battery' in vals.keys() else -1
        pos_data['accuracy'] = vals['acc']
        pos_data['date'] = cur_datetime
        pos_data['dev_id'] = 'ben'
        if 'speed' in vals.keys():
            pos_data['speed'] = vals['spd']
        else:
            pos_data['speed'] = 0
        if 'altitude' in vals.keys():
            pos_data['altitude'] = float(vals['alt'])
        else:
            pos_data['altitude'] = 0
            
        pos_data['source'] = 'gps_logger'

        try:
            response = self.database.insert_location(pos_data)
        except:
            response = {'error': 'true'}

        return Response(response=jsonpickle.encode(response), status=200, mimetype="application/json")


    def calc_map_center(self, lat_list, lon_list):

        min_lat = min(lat_list)
        max_lat = max(lat_list)
        min_lon = min(lon_list)
        max_lon = max(lon_list)

        c_lat = (max_lat - min_lat) / 2 + min_lat
        c_lon = (max_lon - min_lon) / 2 + min_lon

        min_lat *= math.pi / 180
        max_lat *= math.pi / 180
        min_lon *= math.pi / 180
        max_lon *= math.pi / 180

        dlon = max_lon - min_lon
        dlat = max_lat - min_lat

        a = math.sin(dlat / 2)**2 + math.cos(min_lat) * math.cos(max_lat) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        # approximate radius of earth in km
        R = 6373.0
        distance = R * c * 1000 
        distance = max(distance, 20)
        # print(distance)

        num_pix = 800
        meter_per_pix = distance / num_pix

        # Source: https://stackoverflow.com/questions/9356724/google-map-api-zoom-range
        zoom = round(math.log2( 1 / (meter_per_pix / 156543 / math.cos(min_lat)) ))
        zoom = min(zoom, 19)

        # Calculate zoom level
        GLOBE_WIDTH=256
        lat_ang = max_lat - min_lat
        if lat_ang < 0:
            lat_ang += 360

        return c_lat, c_lon, zoom


    @route('/', methods=['GET', 'POST'])
    @cross_origin(origin='*',headers=['Content-Type','Authorization'])
    def main_map(self):

        today = date.today()
        default_start = today - timedelta(days=90)
        default_start = datetime.combine(default_start, datetime.min.time())

        vals = request.args
        if 'start' in vals:
            start, specific_start = self.database.calc_start( vals['start'], default_start='1970')
        else:
            start = default_start # dateutil.parser.parse('1970-1-1')
            specific_start = False
        if 'end' in vals:
            end, specific_end = self.database.calc_end(vals['end'])
        else:
            end = datetime.now()
            specific_end = False

        if end < start:
            et = end
            end = start
            start = et

        start_utc = int(start.strftime('%s'))
        end_utc = int(end.strftime('%s'))
        if specific_start:
            start_datetime = start.strftime('%Y-%m-%d %H:%M:%S')
        else:
            start_datetime = start.strftime('%Y-%m-%d')
        if specific_end:
            end_datetime = end.strftime('%Y-%m-%d %H:%M:%S')
        else:
            end_datetime = end.strftime('%Y-%m-%d')

        data = self.database.retrieve_points(start_utc = start_utc, end_utc = end_utc)

        polyline_path = []
        markers = []

        def even_select(N, M):
            if M > N/2:
                cut = np.ones(N, dtype=int)
                q, r = divmod(N, N-M)
                indices = [q*i + min(i, r) for i in range(N-M)]
                cut[indices] = False
            else:
                cut = np.zeros(N, dtype=int)
                q, r = divmod(N, M)
                indices = [q*i + min(i, r) for i in range(M)]
                cut[indices] = True
            return cut

        if len(data) > 100000:
            idcs = even_select(len(data), 100000)
            idcs = np.where(idcs == 1)[0]
            data = data.iloc[idcs]
            print("Subsampled", len(data))

        # Sample the data evenly so that we have a manageable chunk. 

        if len(data) > 0:

            null_dates = data.datetime.isnull()
            not_null_dates = ~null_dates

            data = data[not_null_dates]

            data_lats = data['lat'].tolist()
            data_lons = data['lon'].tolist()
            data_ids = data['id'].tolist()

            base_url_https = re.sub('^http:', 'https:', request.base_url)

            if 'points' in vals:
                markers = [{'icon': 'http://maps.google.com/mapfiles/ms/icons/green-dot.png', 
                                    'lat': data_lats[ridx], 
                                    'lng': data_lons[ridx],
                                    'infobox': f'''<form action={base_url_https}execute_delete method="post">
                                                   <input type=hidden name=id value={data_ids[ridx]}>
                                                   <button type='submit' name='delete' value='Delete'>Delete Point</button>
                                                   </form>
                                                '''} \
                            for ridx in range(len(data)) ]
            else:
                polyline_path = [{'lat': data_lats[ridx], 'lng': data_lons[ridx]} \
                    for ridx in range(len(data))]

            c_lat, c_lon, zoom = self.calc_map_center(data_lats, data_lons)

        else:
            zoom = 3
            polyline_path = []
            c_lat = 45
            c_lon = -85

        if 'points' in vals:
            sndmap = Map(
                identifier="sndmap",
                lat=c_lat,
                lng=c_lon,
                style=(
                    "height:100%;"
                    "width:100%;"
                    "top:0;"
                    "left:0;"
                    "position:absolute;"
                    "z-index:200;"
                ),
                zoom=zoom,
                # polylines=[polyline_path],
                markers=markers
            )

            return render_template('example.html', map=sndmap, start=start_datetime, end=end_datetime, delete=False, points=True)
        else:
            print("ll", len(polyline_path))

            polyline = {
                "stroke_color": "#0AB0DE",
                "stroke_opacity": 1.0,
                "stroke_weight": 3,
                "path": polyline_path,
            }
            plinemap = Map(
                identifier="plinemap",
                varname="plinemap",
                lat=c_lat,
                lng=c_lon,
                zoom=zoom,
                polylines=[polyline],
                style=(
                    "height:100%;"
                    "width:100%;"
                    "top:0;"
                    "left:0;"
                    "position:absolute;"
                    "z-index:200;"
                ),
            )

            print(plinemap)
            return render_template('example.html', map=plinemap, start=start_datetime, end=end_datetime, delete=False, points=False)



    # This is for loggin ulogger, if you choose. 
    @route('/client/index.php', methods=['GET', 'POST'])
    def ulogger_log(self):
        vals = request.values

        if vals['action'] == 'auth':
            # Fields are user and pass
            return Response(response= jsonpickle.encode({'error': 'false'}), status=200, mimetype="application/json")
        elif vals['action'] == 'addtrack':
            # Fields are track
            return Response(response= jsonpickle.encode({'trackid': '1', 'error': 'false'}), status=200, mimetype="application/json")
        elif vals['action'] == 'addpos':
            pos_data = {}
            
            cur_datetime = datetime.utcfromtimestamp(int(vals['time']))

            pos_data['utc'] = vals['time']
            pos_data['lat'] = vals['lat']
            pos_data['lon'] = vals['lon']
            pos_data['battery'] = vals['battery'] if 'battery' in vals.keys() else -1
            pos_data['accuracy'] = vals['accuracy']
            pos_data['date'] = cur_datetime
            pos_data['dev_id'] = 'ben'
            pos_data['source'] = 'ulogger'

            if vals['provider'] == 'gps':
                pos_data['altitude'] = float(vals['altitude'])
                pos_data['speed'] = vals['speed'] if 'speed' in vals.keys() else 0
            else:
                pos_data['altitude'] = 0
                pos_data['speed'] = 0

            response = self.database.insert_location(pos_data)

            return Response(response= jsonpickle.encode({'error': 'false'}), status=200, mimetype="application/json")

    @route('/execute_delete', methods=['POST'])
    def execute_delete(self):
        print('deleting')
        print(request)
        
        vals = request.form

        if 'id' not in vals:
            resp = {'error': f"The key 'id' was not in the URL payload."}
            return Response(response= jsonpickle.encode(resp), status=200, mimetype="application/json")

        # start_utc, end_utc, lat_top, lat_bot, lon_left, 
        # lon_right, start_datetime, end_datetime = __del_request_prep__(vals)
        # self.database.delete_point(vals)
        del_id = vals['id']
        if type(del_id) == str:
            del_id = int(del_id)

        self.database.delete_by_id(data_id = del_id)

        return Response(response=jsonpickle.encode({"status": "OK", "deleted": del_id}), status=200, mimetype="application/json")




FlaskApp.register(app,route_base = '/')        


if __name__ == '__main__':
    app.run(debug=True, port=8080, host='0.0.0.0')