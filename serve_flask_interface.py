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

from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)


auth = HTTPBasicAuth()

password = os.environ['PASSWORD']
users = {
    "admin": generate_password_hash(password),
    "benjamin": generate_password_hash(password),
}

@auth.verify_password
def verify_password(username, password):
    if username in users and \
            check_password_hash(users.get(username), password):
        return username

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
    route_base = '/'

    # def __init__(self):
    @classmethod
    def _initilization(cls):
        # super(FlaskApp, self).__init__()
        
        with open(config.basic_county_json, 'rb') as geodata:
            cls.counties = json.load(geodata)

        # Edit GEO_ID field to remove the leading values
        for cc in range(len(cls.counties['features'])):
            cls.counties['features'][cc]['properties']['GEO_ID'] = re.sub(r'0500000US', '', cls.counties['features'][cc]['properties']['GEO_ID'])

        cls.database = location_db.locationDB(db_name=config.database_location, \
                                    fips_file = config.county_fips_file, \
                                    country_file=config.country_file)


        cls.colorscale = plotly.colors.sequential.Viridis
        cls.colorscale = cls.colorscale[::-1]
        cls.colorscale_county = cls.colorscale.copy()
        cls.colorscale_county[0] = '#ffeae8'

        cls.template = None
        cls.compute_running = False
        cls.num_counties_visited = 0
        tmp = cls.database.get_county_visits_dataframe()
        cls.num_counties = len(tmp)
        cls.avg_county_year = cls.database.get_average_visit_year()
        del tmp
        print("Init")
        # cls.__precompute_graph()

    def __set_map_layout(self, fig):

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

    def __precompute_graph(self):

        self.compute_running = True
        self.template = None

        county_df = self.database.get_county_visits_dataframe()
        self.avg_county_year = self.database.get_average_visit_year()
        self.num_counties_visited = int(county_df.visited.sum())

        fig = px.choropleth(county_df, geojson=self.counties, locations="FIPS", color='year',
                                   color_continuous_scale=self.colorscale_county,
                                   # range_color=(dmin, dmax),
                                   scope="usa"
                                  )
        fig = self.__set_map_layout(fig)

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        self.template = graphJSON
        self.compute_running = False

    def _compute_table(self, county_df):

        state_list = county_df['state'].unique().tolist()
        state_names = [config.abbrev_to_us_state[st] for st in state_list]

        grouper = county_df[['state', 'visited']].groupby('state')
        n_visited = grouper.sum()
        n_total = grouper.count()
        # Rename the column
        n_total = n_total.rename(mapper = {'visited': 'Total'}, axis=1)
        n_visited = n_visited.rename(mapper = {'visited': 'Visited'}, axis=1)
        # urls = [f'state_view?state={st}' for st in state_list]
        urls = [f"<a class='tbl_btn' href='state_view?state={st}'>View</a>" for st in state_list]
        url_df = pd.DataFrame(list(zip(state_names, urls) ), columns=['Name', 'URL'])
        url_df.index = state_list # list(zip(state_list, urls)))

        n_visited = n_visited.sort_index()
        n_total = n_total.sort_index()
        url_df = url_df.sort_index()
        table = pd.concat((n_visited.T, n_total.T, url_df.T)).T
        table.index = np.arange(len(table))
        table = table.sort_values('Name')

        table_html = table.to_html(escape=False, index=False, columns=['Name', 'Visited', 'Total', 'URL'])

        return table_html

    @route('/state_view', methods=['POST', 'GET'])
    @auth.login_required
    def serve_state_view(self):
        abbrev_to_state = config.abbrev_to_us_state
        state_code = request.values['state'].upper()
        if state_code not in abbrev_to_state.keys():
            return render_template('404.html', error=f"Requested state abbreviation \"{state_code}\" \ndoes not correspond to a US state"), 404
        state_name = abbrev_to_state[state_code]


        county_df = self.database.get_county_visits_dataframe()

        # Filter to a state 
        state_df = county_df[county_df['state'] == state_code]
        # Get the first two digits of the FIPS code in order to filter down the counties. 
        fips_first_two = state_df['FIPS'].iloc[0][:2]
        # Use that to just get a subset of counties in the GEOJSON
        # that correspond to that state.
        counties_list = [c for c in self.counties['features'] if c['id'].startswith(fips_first_two)]
        counties_subset = {'features': counties_list, 'type': self.counties['type']}

        num_visited = len(state_df[state_df.visited == True])
        num_counties = len(state_df)

        visit_string = f" | {num_visited}/{num_counties} counties ({num_visited / num_counties * 100:.2f}%) visited"

        state_df = state_df.replace(True, 'Visited')
        state_df = state_df.replace(False, 'Unvisited')
        state_df = state_df.sort_values('visited')

        if num_visited == num_counties:
            colors = ['#32D172'] # Visited
        else:
            colors = ['#F5F3ED', '#32D172'] # Unvisited, Visited

        # fig = px.choropleth(state_df, geojson=self.counties, locations="FIPS", color='visited',
        fig = px.choropleth(state_df, geojson=counties_subset, locations="FIPS", color='visited',
                                   color_discrete_sequence=colors,
                                   labels={'True':'Visited', 'False':'Unvisited'},
                                   projection='mercator',
                                  )
        if state_code == 'AK':

            fig.update_geos(
                  lonaxis_range=[20, 380],
                  projection_scale=6,
                  center=dict(lat=61),
                  visible=False)
        else:
            fig.update_geos(fitbounds='locations', visible=False)


        fig = self.__set_map_layout(fig)

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        state_urls = self._compute_table(county_df)

        return render_template('notdash.html', \
                               graphJSON=graphJSON, \
                               stat_string=visit_string, \
                               title=state_name,
                               more_html=state_urls)

    @route('/counties')
    @auth.login_required
    def serve_county_graph(self):

        # Check whether the precomputed graph is up to date.
        num_visited = self.database.get_num_counties_visited()
        avg_county_year = self.database.get_average_visit_year()

        if not self.compute_running and (num_visited != self.num_counties_visited or avg_county_year != self.avg_county_year): # or self.template is None:
            # Kick it off again.
            print("Recomputing")
            self.__precompute_graph()

        while self.template is None:
            time.sleep(0.25)

        visited_string = f' - {num_visited}/{self.num_counties} | {num_visited / self.num_counties * 100:.2f}%'

        return render_template('notdash.html', graphJSON=self.template, stat_string=visited_string, title='Visited Counties')
        # return "<h1>This is my indexpage2</h1>"

    @route('/log_country', methods=['POST', 'GET'])
    def log_country(self):
        if 'country' not in request.values.keys():
            return Response(response= jsonpickle.encode({'error': 'Query must by of form "?country=<identifier>"', 'success': False}), status=400, mimetype="application/json")

        identifier = request.values['country']
        country_add_success = self.database.set_visited_country(identifier)
        if country_add_success:
            return Response(response= jsonpickle.encode({'error': "None", 'success': True}), status=200, mimetype="application/json")
        else:
            return render_template('404.html', error=f'Selected identifier "{identifier}" was not found in database.'), 404
            # return Response(response= jsonpickle.encode({'error': f'Selected identifier "{identifier}" was not found in database.', 'success': False}), status=400, mimetype="application/json")

    @route('/countries')
    @auth.login_required
    def serve_country_graph(self):

        county_df = self.database.get_visited_countries()
        num_visited = len(county_df[county_df.visited == True])

        visited = county_df[county_df.visited]

        country_name_list = visited.name.tolist()

        fig = px.choropleth(locationmode="country names", 
                            locations=country_name_list, 
                            hover_name=country_name_list)

        fig = self.__set_map_layout(fig)
        visited_string = f' | {num_visited} Countries Visited'

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        return render_template('notdash.html', graphJSON=graphJSON, stat_string=visited_string, title='Visited Countries')


        # >>> ll = ['USA', 'Mexico', 'Peru', 'Brazil', 'France', "United Kingdom", "Germany"]
        # >>> 
        # >>> fig.show()
        # >>> ll = ['USA', 'Mexico', 'Peru', 'Brazil', 'France', "United Kingdom", "Germany", 'Canada', 'Panama']
        # >>> fig = px.choropleth(locationmode="country names", locations=ll, hover_name=ll)


    @route('/states')
    @auth.login_required
    def serve_state_graph(self):

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

        fig = self.__set_map_layout(fig)
        visited_string = f' | {num_visited}/50 States{" & DC" if dc_visited else ""} Visited'

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        county_df = self.database.get_county_visits_dataframe()
        state_urls = self._compute_table(county_df)
        return render_template('notdash.html', \
                               graphJSON=graphJSON, \
                               stat_string=visited_string, \
                               title='Visited States',
                               more_html = state_urls)


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


    def __calc_map_center(self, lat_list, lon_list):

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
    @auth.login_required
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

            c_lat, c_lon, zoom = self.__calc_map_center(data_lats, data_lons)

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
            # print(polyline_path)

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




# This weird technique, and not having an
# __init__ in the traditional sense, is because the
# register function runs __init__ once for each route.
# Solution is from flask_classful issues at
# https://github.com/pallets-eco/flask-classful/issues/114
# and is admittedly a hack but it works. 
FlaskApp._initilization()
FlaskApp.register(app,route_base = '/')


if __name__ == '__main__':
    print("Run")
    app.run(debug=True, port=8090, host='0.0.0.0')
