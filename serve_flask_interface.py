# Using graph_objects

from datetime import datetime, timedelta, date, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from dotenv import load_dotenv
from flask import Flask, render_template, Response, request, redirect, url_for, abort, make_response
from flask_classful import FlaskView, route
from flask_cors import CORS, cross_origin
from flask_googlemaps import GoogleMaps, Map
from json import dumps
from plotly import utils
from urllib.request import urlopen
from functools import wraps
import config
import requests
import colorsys
import geopandas as gpd
import hashlib
import json
import jsonpickle
import location_db
import math
import numpy as np
import os
import pandas as pd
import plotly
import plotly.express as px
import plotly.graph_objects as go
from shapely.geometry import mapping
from shapely.ops import transform as shapely_transform
import re
import requests
import time
import xmltodict
import dateutil.parser
import pytz
from flask_httpauth import HTTPBasicAuth
# from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# auth = HTTPBasicAuth()

# password = os.environ['PASSWORD']
# users = {
#     "admin": generate_password_hash(password),
#     "benjamin": generate_password_hash(password),
# }

# @auth.verify_password
# def verify_password(username, password):
#     if username in users and \
#            check_password_hash(users.get(username), password):
#        return username

AUTHELIA_URL='https://auth.exploretheworld.tech'

def _clean_redirect_target():
    # Build the URL to send Authelia as 'rd', with any existing 'rd'
    # param stripped out. Without this, a failed verification nests the
    # previous redirect URL into the new one, and the URL grows without
    # bound on repeated failures until it exceeds the server's request
    # line limit.
    other_args = request.args.to_dict()
    other_args.pop('rd', None)
    if other_args:
        return f"{request.base_url}?{urlencode(other_args)}"
    return request.base_url

def authelia_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        clean_url = _clean_redirect_target()

        # 1. Grab the Authelia cookie from the incoming request
        authelia_cookie = request.cookies.get('authelia_session')

        if not authelia_cookie:
            # 2. Redirect to Authelia if no cookie is found
            # 'rd' tells Authelia where to return the user after login
            return redirect(f"{AUTHELIA_URL}/?rd={clean_url}")

        # 3. (Optional but Recommended) Verify the cookie with Authelia's API
        # This prevents someone from just making up a fake cookie
        verify_url = f"{AUTHELIA_URL}/api/verify?rd={clean_url}"
        try:
            # allow_redirects=False: we only care about the status code here.
            # Following Authelia's own redirect chain server-side was the
            # actual cause of the exponential 'rd' nesting bug.
            response = requests.get(verify_url, cookies={'authelia_session': authelia_cookie}, timeout=2, allow_redirects=False)
            if response.status_code != 200:
                # Cookie exists but Authelia says it's expired or logged out
                return redirect(f"{AUTHELIA_URL}/?rd={clean_url}")

        except requests.exceptions.RequestException:
            # If Authelia is down, fail safe and deny access
            abort(503)

        return f(*args, **kwargs)
    return decorated_function


def _wrap_lon(lon):
    # Normalize to [-180, 180). Needed because Alaska's Aleutian
    # Islands cross the antimeridian -- some are recorded as ~-179
    # and others as ~+179, which are geographically adjacent but
    # numerically far apart unless unwrapped/rewrapped consistently.
    return ((lon + 180) % 360) - 180

def _mercator_y(lat_deg):
    lat_rad = math.radians(max(min(lat_deg, 85.05), -85.05))
    return math.log(math.tan(math.pi / 4 + lat_rad / 2))

def _mercator_center_lat(min_lat, max_lat):
    # The visual midpoint of a lat range under Mercator is not the
    # simple degree average -- Mercator stretches increasingly toward
    # the poles, so a naive average sits off-center (biased toward the
    # equator relative to how the range actually renders). Matters
    # most at high latitudes, e.g. Alaska's ~54-71N span.
    y_mid = (_mercator_y(min_lat) + _mercator_y(max_lat)) / 2
    return math.degrees(2 * math.atan(math.exp(y_mid)) - math.pi / 2)

def _fit_zoom(bounds, box_width_px, box_height_px, padding=0.85):
    # Zoom level such that a lon/lat bounding box fits within a given
    # pixel-size box, accounting for the Mercator projection's
    # latitude-dependent vertical scale (a naive degrees-of-latitude
    # calculation would be wrong -- Mercator stretches vertically near
    # the poles). box_width_px/box_height_px are necessarily a fixed
    # assumption of the actual rendered container size, since that
    # isn't known server-side; tuned for a typical desktop window.
    min_lon, min_lat, max_lon, max_lat = bounds
    lon_span = max_lon - min_lon
    y_span = _mercator_y(max_lat) - _mercator_y(min_lat)
    zoom_x = math.log2((box_width_px * padding * 360) / (lon_span * 256))
    zoom_y = math.log2((box_height_px * padding * 2 * math.pi) / (y_span * 256))
    return min(zoom_x, zoom_y)

def _pad_bounds(bounds, pad_degrees):
    min_lon, min_lat, max_lon, max_lat = bounds
    return dict(
            west=_wrap_lon(min_lon - pad_degrees),
            east=_wrap_lon(max_lon + pad_degrees),
            south=max(min_lat - pad_degrees, -85.0),
            north=min(max_lat + pad_degrees, 85.0),
        )

def _country_color(code):
    # A distinct color per visited country instead of one shared
    # "visited" color, so neighboring visited countries don't blend
    # into one blob. Deliberately not doing real four-color-theorem
    # map coloring (needs adjacency data + a constraint solver) -- just
    # a hash-seeded hue per country, so two neighbors can in principle
    # land on similar colors. Hash (not the stdlib `random` module) so
    # each country's color is stable across requests/reloads rather
    # than reshuffling every page load; fixed saturation/lightness so
    # every color comes out equally vivid and legible regardless of
    # which hue a given country happens to land on.
    seed = int(hashlib.md5(code.encode()).hexdigest(), 16)
    hue = (seed % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.50, 0.65)
    return '#{:02x}{:02x}{:02x}'.format(round(r * 255), round(g * 255), round(b * 255))

load_dotenv()

cors = CORS(app, resources={r"/foo": {"origins": "*"}})
# SESSION_TYPE = 'redis'
app.config.from_object(__name__)
app.config['CORS_HEADERS'] = 'Content-Type'
app.config['TEMPLATES_AUTO_RELOAD'] = True
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

        # World country outlines for the /countries choropleth, id'd by
        # ISO alpha-3 code (matches location_db's countries.code_3) --
        # see config.world_country_json for provenance.
        with open(config.world_country_json, 'rb') as geodata:
            cls.world_countries_geojson = json.load(geodata)

        # Precompute lon/lat bounds for the Alaska/Hawaii inset maps,
        # so their default center/zoom and pan limits are derived from
        # the actual geography instead of guessed constants.
        counties_gdf = gpd.GeoDataFrame.from_features(cls.counties['features'])
        ak_gdf = counties_gdf[counties_gdf['GEO_ID'].str.startswith('02')].copy()
        # Unwrap the Aleutians across the antimeridian (see _wrap_lon)
        # before taking bounds, or the islands on either side of 180
        # longitude make Alaska look like it spans the whole globe.
        ak_gdf['geometry'] = ak_gdf['geometry'].apply(
                lambda geom: shapely_transform(lambda x, y: (x - 360 if x > 0 else x, y), geom))
        # Aleutians West alone drags the bounds out to -187 (every
        # other AK county stays within -173 to -141) -- excluded here
        # so the inset's default zoom/pan fits the bulk of the state
        # instead of being dominated by one remote, thinly-populated
        # census area. It still renders normally on the map itself,
        # just outside this inset's default pan range.
        ak_fit_gdf = ak_gdf[ak_gdf['NAME'] != 'Aleutians West']
        cls.ak_bounds = tuple(ak_fit_gdf.total_bounds)
        cls.hi_bounds = tuple(counties_gdf[counties_gdf['GEO_ID'].str.startswith('15')].total_bounds)
        # 02/15 = AK/HI (their own insets); 72/78/66/60/69 = Puerto
        # Rico/Virgin Islands/Guam/American Samoa/Northern Mariana --
        # present in the county data and otherwise drags the "fit the
        # continental US" bounds far south/east.
        non_conti_fips = ['02', '15', '72', '78', '66', '60', '69']
        is_conti = ~counties_gdf['GEO_ID'].str[:2].isin(non_conti_fips)
        cls.conti_bounds = tuple(counties_gdf[is_conti].total_bounds)

        cls.database = location_db.locationDB(db_name=config.database_location, \
                                    fips_file = config.county_fips_file, \
                                    country_file=config.country_file)

        # State-level outlines for the /states choropleth: dissolve the
        # county polygons already loaded above up to state boundaries,
        # rather than sourcing a whole separate states GeoJSON -- we
        # already have every county's geometry and know its state.
        county_state_lookup = cls.database.get_county_visits_dataframe()
        fips_to_state = dict(zip(county_state_lookup['FIPS'], county_state_lookup['state']))
        states_gdf = counties_gdf.copy()
        states_gdf['state_abbrev'] = states_gdf['GEO_ID'].map(fips_to_state)
        states_gdf = states_gdf.dropna(subset=['state_abbrev'])
        states_gdf = states_gdf.dissolve(by='state_abbrev').reset_index()
        cls.states_geojson = {
                'type': 'FeatureCollection',
                'features': [
                        {
                            'type': 'Feature',
                            'id': row['state_abbrev'],
                            'properties': {'name': config.abbrev_to_us_state.get(row['state_abbrev'], row['state_abbrev'])},
                            'geometry': mapping(row['geometry']),
                        }
                        for _, row in states_gdf.iterrows()
                    ],
            }

        # Name/code list for the Add Country autocomplete (see
        # inject_country_list() below) -- name/codes are static once
        # seeded, so this is computed once here rather than re-queried
        # on every page load.
        all_countries_df = cls.database.get_all_countries_dataframe()
        cls.country_list_json = json.dumps(
                all_countries_df[['name', 'iso_2', 'iso_3']].to_dict('records'))

        cls.colorscale = plotly.colors.sequential.Viridis
        #n_colors = 40
        #cls.colorscale = px.colors.sample_colorscale("viridis", [n/(n_colors -1) for n in range(n_colors)])
        cls.colorscale = cls.colorscale[::-1]
        # cls.colorscale = ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725', '#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
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
            )

        # Plotly allocates the geo subplot a fixed-size rectangle
        # ("domain") within the figure that doesn't necessarily fill
        # the whole container -- panning/zooming moves the map inside
        # that rectangle rather than growing the rectangle itself,
        # which is what made the map look boxed-in even once the
        # surrounding CSS was full-bleed. Force it to the full figure.
        fig.update_geos(domain=dict(x=[0, 1], y=[0, 1]))

        return fig

    def __mapbox_layout_base(self):
        # Continental + Alaska/Hawaii mapbox subplot layout, shared by
        # /counties and /states -- both need the same "Alaska is far
        # away" inset treatment (mapbox has no native inset projection
        # the way scope="usa" geo traces do), fit to Alaska/Hawaii's
        # true geographic bounds (computed once in _initilization).
        # Purely geometric -- independent of whatever data (counties'
        # or states' visited/year) ends up colored on top.
        ref_chart_px = (1400, 800)
        ak_domain = dict(x=[0.01, 0.28], y=[0.02, 0.42])
        hi_domain = dict(x=[0.31, 0.50], y=[0.02, 0.24])

        ak_box_px = (ref_chart_px[0] * (ak_domain['x'][1] - ak_domain['x'][0]),
                     ref_chart_px[1] * (ak_domain['y'][1] - ak_domain['y'][0]))
        hi_box_px = (ref_chart_px[0] * (hi_domain['x'][1] - hi_domain['x'][0]),
                     ref_chart_px[1] * (hi_domain['y'][1] - hi_domain['y'][0]))

        ak_zoom = _fit_zoom(self.ak_bounds, *ak_box_px)
        hi_zoom = _fit_zoom(self.hi_bounds, *hi_box_px)
        ak_center = dict(lon=(self.ak_bounds[0] + self.ak_bounds[2]) / 2,
                          lat=_mercator_center_lat(self.ak_bounds[1], self.ak_bounds[3]))
        hi_center = dict(lon=(self.hi_bounds[0] + self.hi_bounds[2]) / 2,
                          lat=_mercator_center_lat(self.hi_bounds[1], self.hi_bounds[3]))

        # Limit how far each inset can be panned/zoomed out to roughly
        # a few degrees past the state's real boundary, rather than
        # letting a small inset pan off into empty ocean.
        ak_pan_bounds = _pad_bounds(self.ak_bounds, pad_degrees=3)
        hi_pan_bounds = _pad_bounds(self.hi_bounds, pad_degrees=3)

        return dict(
                mapbox=dict(
                        style='carto-positron',
                        center=dict(lat=39.5, lon=-98.35),
                        zoom=3.3,
                        domain=dict(x=[0, 1], y=[0, 1]),
                    ),
                # Small insets in the bottom-left corner, same spot
                # the usual USA-map convention places them.
                mapbox2=dict(
                        style='carto-positron',
                        center=ak_center,
                        zoom=ak_zoom,
                        domain=ak_domain,
                        bounds=ak_pan_bounds,
                    ),
                mapbox3=dict(
                        style='carto-positron',
                        center=hi_center,
                        zoom=hi_zoom,
                        domain=hi_domain,
                        bounds=hi_pan_bounds,
                    ),
            )

    def __precompute_graph(self):

        self.compute_running = True
        self.template = None

        county_df = self.database.get_county_visits_dataframe()

        visited_df = county_df[county_df['visited']==True]
        self.avg_county_year = self.database.get_average_visit_year()
        self.num_counties_visited = int(county_df.visited.sum())

        # county_df['year'] is -1 for never-visited, else (real year -
        # 2000) -- see location_db.get_county_visits_dataframe(). Used
        # to bound the client-side year slider.
        visited_years = county_df.loc[county_df['year'] > -1, 'year']
        if len(visited_years) > 0:
            self.year_min = int(visited_years.min()) + 2000
            self.year_max = int(visited_years.max()) + 2000
        else:
            self.year_min = self.year_max = datetime.now().year

        # Three separate mapbox subplots (continental US, plus small
        # Alaska/Hawaii insets) instead of a single geo/choropleth
        # trace. A geo trace with scope="usa" is a static, fixed-aspect
        # SVG projection -- it always letterboxes inside a container
        # whose shape doesn't match, and panning/zooming only moves
        # content within that same fixed-size canvas, which is what
        # made the map look "stuck in a box" no matter how far zoomed.
        # A mapbox trace is a real pannable/zoomable tile map that
        # fills its domain at any aspect ratio -- but mapbox has no
        # native inset concept the way scope="usa"'s Albers projection
        # does, so Alaska/Hawaii also get their own small subplots for
        # an always-visible view, in addition to (not instead of)
        # rendering at their true, far-away location on the main map --
        # the main map is a real geographic view now, so panning/
        # zooming out to actually reach them should show them colored,
        # not a blank basemap.
        main_df = county_df
        ak_df = county_df[county_df['state'] == 'AK']
        hi_df = county_df[county_df['state'] == 'HI']

        fig = go.Figure()

        fig.add_trace(go.Choroplethmapbox(
                geojson=self.counties, locations=main_df['FIPS'], z=main_df['year'],
                coloraxis='coloraxis', subplot='mapbox',
                marker_line_width=0.4, marker_line_color='#888',
            ))
        fig.add_trace(go.Choroplethmapbox(
                geojson=self.counties, locations=ak_df['FIPS'], z=ak_df['year'],
                coloraxis='coloraxis', subplot='mapbox2',
                marker_line_width=0.4, marker_line_color='#888',
            ))
        fig.add_trace(go.Choroplethmapbox(
                geojson=self.counties, locations=hi_df['FIPS'], z=hi_df['year'],
                coloraxis='coloraxis', subplot='mapbox3',
                marker_line_width=0.4, marker_line_color='#888',
            ))
        # State-boundary overlay on the main map only (not the AK/HI
        # insets, which are already single-state views) -- a second
        # trace drawn on top, transparent fill (its z/colorscale are
        # irrelevant, chosen only so no fill color shows) and a
        # thicker/darker line than the county borders below it, so
        # state lines read clearly at a glance even zoomed into county
        # detail. hoverinfo='skip' keeps it from swallowing hover
        # tooltips meant for the county layer underneath.
        fig.add_trace(go.Choroplethmapbox(
                geojson=self.states_geojson,
                locations=[f['id'] for f in self.states_geojson['features']],
                z=[0] * len(self.states_geojson['features']),
                colorscale=[[0, 'rgba(0,0,0,0)'], [1, 'rgba(0,0,0,0)']],
                showscale=False, subplot='mapbox',
                marker_line_width=1.5, marker_line_color='#333',
                hoverinfo='skip',
            ))

        fig.update_layout(
                # showscale=False: replaced by the interactive year
                # slider below, which does the colorbar's old job.
                coloraxis=dict(colorscale=self.colorscale_county, showscale=False),
                **self.__mapbox_layout_base(),
            )

        fig = self.__set_map_layout(fig)

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        self.template = graphJSON
        self.compute_running = False

    def _compute_table(self, county_df):

        grouper = county_df[['state', 'visited']].groupby('state')
        n_visited = grouper.sum().rename(mapper = {'visited': 'Visited'}, axis=1)
        n_total = grouper.count().rename(mapper = {'visited': 'Total'}, axis=1)

        # Concatenating on axis=1 aligns both series by their shared
        # index (state abbreviation), so this doesn't depend on both
        # sides happening to already be sorted the same way.
        table = pd.concat((n_visited, n_total), axis=1)
        table['Name'] = [config.abbrev_to_us_state[st] for st in table.index]
        table = table.sort_values('Name')

        # A responsive card grid instead of a plain <table>: table rows
        # can't reflow into multiple columns via CSS, but a grid of
        # cards can -- one per row on narrow/mobile screens, several
        # per row on wide ones, purely from available width.
        cards = []
        for abbrev, row in table.iterrows():
            cards.append(
                f"<a class='state-card' href='state_view?state={abbrev}'>"
                f"<span class='state-card-name'>{row['Name']}</span>"
                f"<span class='state-card-stat'>{int(row['Visited'])}/{int(row['Total'])} counties</span>"
                f"</a>"
            )

        return "<div class='state-grid'>" + "".join(cards) + "</div>"

    def _compute_country_cards(self, country_df):
        # Same card-grid look as _compute_table's state list, but no
        # href -- there's no per-country drill-down page the way
        # state_view is a drill-down from the state list.
        visited_df = country_df[country_df['visited'] == True].sort_values('name')

        cards = []
        for _, row in visited_df.iterrows():
            cards.append(
                f"<div class='state-card'>"
                f"<span class='state-card-name'>{row['name']}</span>"
                f"<span class='state-card-stat'>{row['iso_3']}</span>"
                f"</div>"
            )

        return "<div class='state-grid'>" + "".join(cards) + "</div>"

    @route('/state_view', methods=['POST', 'GET'])
    @authelia_required
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
                               page_title=f"OwnTracks - State View: {state_name}",
                               more_html=state_urls)

    @route('/counties')
    @authelia_required
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

        # The server can't know the visitor's actual screen size, so
        # the zoom/center baked into the figure above is only a
        # reasonable first-paint guess (tuned for a desktop window).
        # These bounds let the page correct each subplot's zoom
        # client-side, against its real rendered pixel size, right
        # after the map draws.
        mapbox_bounds_json = json.dumps({
                'mapbox': list(map(float, self.conti_bounds)),
                'mapbox2': list(map(float, self.ak_bounds)),
                'mapbox3': list(map(float, self.hi_bounds)),
                'yearRange': [self.year_min, self.year_max],
            })

        return render_template('notdash.html',
                graphJSON=self.template,
                stat_string=visited_string,
                title='Visited Counties',
                page_title='OwnTracks - Visited Counties',
                full_bleed_map=True,
                mapbox_bounds_json=mapbox_bounds_json)
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
    @authelia_required
    def serve_country_graph(self):

        country_df = self.database.get_all_countries_dataframe()
        num_visited = int(country_df.visited.sum())

        # Same go.Choroplethmapbox approach as /counties -- a real
        # pannable/zoomable tile map instead of the old static geo
        # trace, so it isn't letterboxed inside its container. Just one
        # subplot (no AK/HI-style insets needed for a world map).
        #
        # Each visited country gets its own color (see _country_color)
        # instead of one shared "visited" color, plus a single shared
        # color for every unvisited country. A single z/colorscale
        # normally means one continuous gradient, so this builds a
        # "stepped" colorscale instead: two colorscale stops at the
        # start/end of each country's z-slice, both the same color,
        # which creates a hard-edged flat block rather than a gradient
        # into its neighbors' slices. category 0 = unvisited; each
        # visited country gets its own category 1..N, so it gets its
        # own single-color slice.
        visited_codes = sorted(country_df.loc[country_df['visited'] == True, 'iso_3'])
        iso3_to_category = {code: i + 1 for i, code in enumerate(visited_codes)}
        country_df['color_category'] = country_df['iso_3'].map(iso3_to_category).fillna(0).astype(int)

        num_categories = len(visited_codes) + 1
        palette = ['#F5F3ED'] + [_country_color(code) for code in visited_codes]
        colorscale = []
        for k, color in enumerate(palette):
            colorscale.append([k / num_categories, color])
            colorscale.append([(k + 1) / num_categories, color])

        fig = go.Figure()
        fig.add_trace(go.Choroplethmapbox(
                geojson=self.world_countries_geojson, locations=country_df['iso_3'],
                # +0.5: the middle of each category's z-slice, so it's
                # unambiguously inside its own step rather than sitting
                # right on a boundary between two colors.
                z=country_df['color_category'] + 0.5, zmin=0, zmax=num_categories,
                coloraxis='coloraxis', subplot='mapbox',
                marker_line_width=0.4, marker_line_color='#888',
            ))

        fig.update_layout(
                coloraxis=dict(colorscale=colorscale, showscale=False),
                mapbox=dict(
                        style='carto-positron',
                        center=dict(lat=20, lon=0),
                        # A fixed, eyeballed default (like the
                        # continental US subplot's zoom=3.3) rather
                        # than a bounds-fit calculation -- fitting the
                        # world's *true* lat extent pulls the center
                        # toward the high-Arctic countries, which looks
                        # wrong for a "world overview" default. The
                        # user can freely pan/zoom from here.
                        zoom=0.8,
                        domain=dict(x=[0, 1], y=[0, 1]),
                    ),
            )

        fig = self.__set_map_layout(fig)
        visited_string = f' | {num_visited} Countries Visited'

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        country_cards = self._compute_country_cards(country_df)

        return render_template('notdash.html',
            graphJSON=graphJSON,
            stat_string=visited_string,
            title='Visited Countries',
            more_html=country_cards,
            full_bleed_map=True,
            page_title='OwnTracks - Visited Countries')


    @route('/states')
    @authelia_required
    def serve_state_graph(self):

        state_df = self.database.get_state_visits_dataframe()
        num_visited = len(state_df[state_df.visited == True])

        dc_visited = bool(state_df[state_df.state == 'DC'].visited.any())
        if dc_visited:
            num_visited -= 1

        # Same go.Choroplethmapbox + continental/AK/HI inset approach
        # as /counties (states has the same "Alaska is far away"
        # problem), colored by visit year -- unlike /countries, states
        # does track that, so keep the gradient + year slider instead
        # of switching to a binary visited/unvisited color. State
        # outlines come from self.states_geojson (counties dissolved up
        # to state boundaries at startup, see _initilization). AK/HI
        # are included on the main map (not just their insets) so
        # panning/zooming out to their true location shows them
        # colored rather than a blank basemap.
        main_df = state_df
        ak_df = state_df[state_df['state'] == 'AK']
        hi_df = state_df[state_df['state'] == 'HI']

        fig = go.Figure()
        fig.add_trace(go.Choroplethmapbox(
                geojson=self.states_geojson, locations=main_df['state'], z=main_df['year'],
                coloraxis='coloraxis', subplot='mapbox',
                marker_line_width=0.4, marker_line_color='#888',
            ))
        fig.add_trace(go.Choroplethmapbox(
                geojson=self.states_geojson, locations=ak_df['state'], z=ak_df['year'],
                coloraxis='coloraxis', subplot='mapbox2',
                marker_line_width=0.4, marker_line_color='#888',
            ))
        fig.add_trace(go.Choroplethmapbox(
                geojson=self.states_geojson, locations=hi_df['state'], z=hi_df['year'],
                coloraxis='coloraxis', subplot='mapbox3',
                marker_line_width=0.4, marker_line_color='#888',
            ))

        fig.update_layout(
                coloraxis=dict(colorscale=self.colorscale_county, showscale=False),
                **self.__mapbox_layout_base(),
            )

        fig = self.__set_map_layout(fig)
        visited_string = f' | {num_visited}/50 States{" & DC" if dc_visited else ""} Visited'

        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        county_df = self.database.get_county_visits_dataframe()
        state_cards = self._compute_table(county_df)

        # state_df['year'] is -1 for never-visited, else (real year -
        # 2000) -- see location_db.get_state_visits_dataframe(). Used
        # to bound the client-side year slider, same as /counties.
        visited_years = state_df.loc[state_df['year'] > -1, 'year']
        if len(visited_years) > 0:
            year_min = int(visited_years.min()) + 2000
            year_max = int(visited_years.max()) + 2000
        else:
            year_min = year_max = datetime.now().year

        mapbox_bounds_json = json.dumps({
                'mapbox': list(map(float, self.conti_bounds)),
                'mapbox2': list(map(float, self.ak_bounds)),
                'mapbox3': list(map(float, self.hi_bounds)),
                'yearRange': [year_min, year_max],
            })

        return render_template('notdash.html',
                graphJSON=graphJSON,
                stat_string=visited_string,
                title='Visited States',
                page_title='OwnTracks - Visited States',
                more_html=state_cards,
                full_bleed_map=True,
                mapbox_bounds_json=mapbox_bounds_json)


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
    @authelia_required
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

            return render_template('mapview.html', map=sndmap, start=start_datetime, end=end_datetime, delete=False, points=True)
        else:
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
            return render_template('mapview.html', map=plinemap, start=start_datetime, end=end_datetime, delete=False, points=False)



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


    @route('/log_flight', methods=['POST', 'GET'])
    def log_flight(self):
        test = False
        data_file = '/data/tmp_flight.kml'

        if request.method == 'POST':
            url = request.form['flight_kml']

            if not test:
                if 'flightaware.com' not in url:
                    return render_template('flight_log_form.html', message=f'Non flightaware url: {url}')

                try:
                    req = Request(
                        url=url,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )

                except:
                    return render_template('flight_log_form.html', message=f'Bad url: {url}')

                webpage = urlopen(req).read()
                web_decode = webpage.decode('utf-8')

                with open(data_file, "w") as file:
                    print(web_decode, file=file)

            ##### Now we do this regardless.
            print("Proess")
            uuid = self.database.get_user_id('ben')


            with open(data_file, 'r') as fh:
                data = fh.read()

            data = xmltodict.parse(data)
    
            when = data['kml']['Document']['Placemark'][2]['gx:Track']['when']
            where = data['kml']['Document']['Placemark'][2]['gx:Track']['gx:coord']

            assert len(when) == len(where)

            for ptidx in range(len(when)):
                zulutime = when[ptidx]
                loc = where[ptidx]
                lon, lat, alt = loc.split(' ')
                lat = float(lat)
                lon = float(lon)
                alt = float(alt)
                timeiso = dateutil.parser.isoparse(zulutime).astimezone(timezone.utc)
                utc_time  = int(timeiso.timestamp())

                pos_data = {}
                pos_data['uuid'] = uuid
                pos_data['dev_id'] = 'ben'
                pos_data['utc'] = utc_time
                pos_data['lat'] = lat
                pos_data['lon'] = lon
                pos_data['battery'] = -1
                pos_data['accuracy'] = -1
                pos_data['date'] = timeiso
                pos_data['altitude'] = alt
                pos_data['speed'] = 0
                pos_data['source'] = 'hist'

                self.database.insert_location(pos_data)

            return redirect(url_for('FlaskApp:main_map'))
        return render_template('flight_log_form.html')

    @route('/logout')
    def logout(self):
        # 1. Clear any local Flask session data if you use it
        # session.clear() 
        target = f"{AUTHELIA_URL}/logout?rd={request.url_root}"
        response = make_response(redirect(target))
    
        # 2. Explicitly clear the cookie on the browser
        # Replace 'example.com' with your actual root domain
        response.set_cookie('authelia_session', '', expires=0, domain='.exploretheworld.tech')
    
        # 2. Redirect to Authelia's logout, which then sends them back to your app
        # After Authelia logs out, the user will be unauthenticated next time they visit.
        return response


# The Add Country form lives in the shared top nav (.country-bar),
# rendered on every page, so its autocomplete data needs to be in
# every template's context rather than just one route's.
@app.context_processor
def inject_country_list():
    return dict(country_list_json=FlaskApp.country_list_json)


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
