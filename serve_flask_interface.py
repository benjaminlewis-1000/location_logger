#! /usr/bin/env python

import flask
import numpy as np

from flask import Flask, request, Response, session, redirect, render_template, request, abort, jsonify
from flask_cors import CORS, cross_origin
from flask_session import Session
import jsonpickle
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float
from sqlalchemy import create_engine
import sqlalchemy
from sqlalchemy.sql import select
import geocoder
from datetime import datetime, timedelta, date
import re
import requests
import json
import urllib
import os
from calendar import timegm
import time
import math
from flask_googlemaps import GoogleMaps, Map
from werkzeug.utils import secure_filename
import dateutil
import location_db
import dateutil.parser
import config

# USGS Elevation Point Query Service
url = r'https://nationalmap.gov/epqs/pqs.php?'

def elevation_function(lat, lon):

    # define rest query params
    params = {
        'output': 'json',
        'x': lon,
        'y': lat,
        'units': 'Meters'
    }

    # format query string and return query value
    result = requests.get((url + urllib.parse.urlencode(params)))
    return result.json()['USGS_Elevation_Point_Query_Service']['Elevation_Query']['Elevation']


database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)

# engine = create_engine('sqlite:////data/location.sqlite', echo=False)
# conn = engine.connect()

# metadata = MetaData()
# users = Table('users', metadata,
#         Column('id', Integer, primary_key=True),
#         Column('dev_id', String),
#     )

# positions = Table('positions', metadata,
#         Column('id', Integer, primary_key=True),
#         Column('date', DateTime),
#         Column('utc_time', Float, index=True),
#         Column('user_id', None, ForeignKey('users.id')),
#         Column('latitude', Float),
#         Column('longitude', Float),
#         Column('altitude', Float),
#         Column('battery', Integer),
#         Column('accuracy', Float),
#         Column('speed', Float),
#         Column('source', String)
#     )

# metadata.create_all(engine)

# Initialize the Flask application
app = Flask(__name__)
cors = CORS(app, resources={r"/foo": {"origins": "*"}})
# SESSION_TYPE = 'redis'
app.config.from_object(__name__)
app.config['CORS_HEADERS'] = 'Content-Type'
app.config['GOOGLEMAPS_KEY'] = os.environ['GMAP_API_KEY']
# print(os.environ['GMAP_API_KEY'])
app.config['UPLOAD_FOLDER'] = "/data"
GoogleMaps(app)



@app.route('/log', methods=['GET', 'POST'])
# https://owntracks.exploretheworld.tech/log
# HTTP body: %ALL
# lat=%LAT&lon=%LON&timestamp=%TIMESTAMP&battery=%BATT&acc=%ACC&spd=%SPD
def alive():

    data = request.data.decode('utf-8')
    data = data.split('&')
    print(data)
    vals = {a.split('=')[0]:a.split('=')[1] for a in data if a != ''}
    print(data, vals, request)
    

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
    print(pos_data)

    try:
        response = database.insert_location(pos_data)
        print(response)
    except:
        print("Bad response...")
        response = {'error': 'true'}
#        Response(response= jsonpickle.encode({'error': 'false'}), status=200, mimetype="application/json")

    return Response(response=jsonpickle.encode(response), status=200, mimetype="application/json")

def calc_map_center(lat_list, lon_list):

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
    # print(zoom)


    # Calculate zoom level
    GLOBE_WIDTH=256
    lat_ang = max_lat - min_lat
    if lat_ang < 0:
        lat_ang += 360

    return c_lat, c_lon, zoom

# def calc_start(start_string, default_start='now'):
#     assert default_start in ['now', '1970']
#     if re.match('^\d\d$', start_string) or re.match('^\d\d\d\d$', start_string):
#         start_string = start_string + '-01-01'
#     try:
#         start = dateutil.parser.parse(start_string)
#         if re.match('^\d\d.?\d\d$', start_string) or re.match('^\d\d\d\d.?\d\d$', start_string):
#             start = start + dateutil.relativedelta.relativedelta(day=1)
#     except:
#         if default_start == '1970':
#             start = dateutil.parser.parse('1970-1-1')
#         else:
#             start = datetime.now()

#     if re.match('\d+-\d+.?\d+ \d+.?\d+.?\d+', start_string):
#         specific = True
#     else:
#         specific = False

#     return start, specific

# def calc_end(end_string, default_end='now'):

#     assert default_end in ['now', '1970']

#     if re.match('\d+-\d+.?\d+ \d+.?\d+.?\d+', end_string):
#         specific = True
#     else:
#         specific = False  

#     if re.match('^\d\d$', end_string) or re.match('^\d\d\d\d$', end_string):
#         end_string = end_string + '-12-31'
#     try:
#         end = dateutil.parser.parse(end_string)
#         if re.match('^\d\d.?\d\d$', end_string) or re.match('^\d\d\d\d.?\d\d$', end_string):
#             end = end + dateutil.relativedelta.relativedelta(day=31)
#         if not specific:
#             end = end + dateutil.relativedelta.relativedelta(hour=23, minute=59, second=59)
#     except:
#         end = datetime.now()
      
#     return end, specific

@app.route('/', methods=['GET', 'POST'])
@cross_origin(origin='*',headers=['Content-Type','Authorization'])
def view():
    print("Posting!")
    print(request)


    today = date.today()
    default_start = today - timedelta(days=90)
    default_start = datetime.combine(default_start, datetime.min.time())

    vals = request.args
    if 'start' in vals:
        start, specific_start = database.calc_start( vals['start'], default_start='1970')
    else:
        start = default_start # dateutil.parser.parse('1970-1-1')
        specific_start = False
    if 'end' in vals:
        end, specific_end = database.calc_end(vals['end'])
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

    data = database.retrieve_points(start_utc = start_utc, end_utc = end_utc)

    polyline_path = []
    markers = []

    print(len(data))

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

    print(len(data))
    if len(data) > 0:
        print(data)

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
       #  for ridx in range(len(data)):

       # # <form class="form-inline" action="/execute_delete", method=post>
       # #    <input type=hidden value={{ request.args.get('start_date') }} name=start_date >
       # #    <input type=hidden value={{ request.args.get('end_date') }} name=end_date >
       # #    <input type=hidden value={{ request.args.get('lon_left') }} name=lon_left >
       # #    <input type=hidden value={{ request.args.get('lon_right') }} name=lon_right >
       # #    <input type=hidden value={{ request.args.get('lat_top') }} name=lat_top >
       # #    <input type=hidden value={{ request.args.get('lat_bot') }} name=lat_bot >
       # #    <button type="submit">Delete Points</button>
       # #  </form> 
                
       #      if 'points' in vals:
       #          redir_element = 
       #          markers.append({'icon': 'http://maps.google.com/mapfiles/ms/icons/green-dot.png', 
       #                          'lat': data_lats[ridx], 
       #                          'lng': data_lons[ridx],
       #                          'infobox': redir_element,
       #                          })
       #      else:
       #          polyline_path.append({'lat': data_lats[ridx], 'lng': data_lons[ridx]})


        c_lat, c_lon, zoom = calc_map_center(data_lats, data_lons)

    else:
        zoom = 3
        polyline_path = []
        c_lat = 45
        c_lon = -85

    print(c_lat, c_lon, zoom)

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

        
    # return flask.render_template('test_temp.html', len=len(data_array), data=data_array)
    
    # return Response(response= jsonpickle.encode({'message': 'logged'}), status=200, mimetype="application/json")


@app.route('/client/index.php', methods=['GET', 'POST'])
def view3():
    vals = request.values
    print(request, vals)
    print(vals['action'])

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

        response = database.insert_location(pos_data)

        return Response(response= jsonpickle.encode({'error': 'false'}), status=200, mimetype="application/json")


# def __del_request_prep__(vals):

#     assert 'start_date' in vals
#     assert 'end_date' in vals
#     assert 'lat_top' in vals
#     assert 'lat_bot' in vals
#     assert 'lon_left' in vals
#     assert 'lon_right' in vals
        
#     sval = vals['start_date']
#     start, specific_start = calc_start( vals['start_date'], default_start='now')
#     end, specific_end = calc_end(vals['end_date'])

#     start_utc = int(start.strftime('%s'))
#     end_utc = int(end.strftime('%s'))
#     lat_top = float(vals['lat_top'])
#     lat_bot = float(vals['lat_bot'])
#     lon_left = float(vals['lon_left'])
#     lon_right = float(vals['lon_right'])

#     if specific_start:
#         start_datetime = start.strftime('%Y-%m-%d %H:%M:%S')
#     else:
#         start_datetime = start.strftime('%Y-%m-%d')
#     if specific_end:
#         end_datetime = start.strftime('%Y-%m-%d %H:%M:%S')
#     else:
#         end_datetime = end.strftime('%Y-%m-%d')

#     return start_utc, end_utc, lat_top, lat_bot, lon_left, lon_right, start_datetime, end_datetime



'''
# Not sure if this can be deleted? 
@app.route('/delete_points', methods=['GET', 'POST'])
def del_pt():
    vals = request.values

    for req_val in ['start_date', 'end_date', 'lat_top', 'lat_bot', 'lon_left', 'lon_right']:
        if not req_val in vals:
            resp = {'error': f"The key {req_val} was not in the URL."}
            return Response(response= jsonpickle.encode(resp), status=200, mimetype="application/json")

    start_utc, end_utc, lat_top, lat_bot, lon_left, lon_right, start_datetime, end_datetime = __del_request_prep__(vals)

    pc = positions.c
    pos_qry = select([positions])\
        .where(pc.utc_time >= start_utc)\
        .where(pc.utc_time <= end_utc)\
        .where(pc.latitude >= lat_bot)\
        .where(pc.latitude <= lat_top)\
        .where(pc.longitude >= lon_left)\
        .where(pc.longitude <= lon_right)\
        .order_by(pc.utc_time.asc())

    data = conn.execute(pos_qry)
    data = data.fetchall()

    data_array = []
    polyline_path = []
    markers = []
    if len(data) > 0:
        for r in data:

            r_dict = dict(r)
            dict_date = r_dict['date'].strftime('%Y-%m-%dT%H:%M:%S')
            data_array.append(r_dict)
            polyline_path.append({'lat': r_dict['latitude'], 'lng': r_dict['longitude']})
            markers.append({'icon': 'http://maps.google.com/mapfiles/ms/icons/green-dot.png', 
                           'lat': r_dict['latitude'], 
                           'lng': r_dict['longitude']})
            # markers.append(  (r_dict['latitude'], r_dict['longitude']) )

        c_lat, c_lon, zoom = calc_map_center(markers)

    else:
        zoom = 3
        polyline_path = []
        c_lat = 45
        c_lon = -85

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

    return render_template('example.html', map=sndmap, start=start_datetime, end=end_datetime, delete=True)

    # return Response(response= jsonpickle.encode({'num_pts': len(data)}), status=200, mimetype="application/json")
    # return render_template('example.html', num_pts = len(data))
'''

@app.route('/execute_delete', methods=['POST'])
def delete_execute():
    
    print(request.form)
    vals = request.form
    
    if 'id' not in vals:
        resp = {'error': f"The key 'id' was not in the URL payload."}
        return Response(response= jsonpickle.encode(resp), status=200, mimetype="application/json")

    # start_utc, end_utc, lat_top, lat_bot, lon_left, 
    # lon_right, start_datetime, end_datetime = __del_request_prep__(vals)
    # database.delete_point(vals)
    database.delete_by_id(data_id = vals['id'])

    
    return Response(response=jsonpickle.encode({"status": "OK"}), status=200, mimetype="application/json")



if __name__ == '__main__':
   app.run(debug = True)

# %LAT, LON, DESC, SAT, ALT, SPD, ACC, DIR, TIMESTAMP, BATT, AID, D


# @app.route('/maps', methods=['GET', 'POST'])
# def mapview():
#     # creating a map in the view
#     mymap = Map(
#         identifier="view-side",
#         lat=37.4419,
#         lng=-122.1419,
#         markers=[(37.4419, -122.1419)],
#         fullscreen_control=True,
#         style=(
#             "height:100%;"
#             "width:100%;"
#             "top:0;"
#             "left:0;"
#             "position:absolute;"
#             "z-index:200;"
#         ),
#     )

#     # polyline = {
#     #     "stroke_color": "#0AB0DE",
#     #     "stroke_opacity": 1.0,
#     #     "stroke_weight": 3,
#     #     "path": [
#     #         {"lat": 33.678, "lng": -116.243},
#     #         {"lat": 33.679, "lng": -116.244},
#     #         {"lat": 33.680, "lng": -116.250},
#     #         {"lat": 33.681, "lng": -116.239},
#     #         {"lat": 33.678, "lng": -116.243},
#     #     ],
#     # }

#     sndmap = Map(
#         identifier="sndmap",
#         lat=37.4419,
#         lng=-122.1419,
#         style=(
#             "height:100%;"
#             "width:100%;"
#             "top:0;"
#             "left:0;"
#             "position:absolute;"
#             "z-index:200;"
#         ),
#         markers=[
#           {
#              'icon': 'http://maps.google.com/mapfiles/ms/icons/green-dot.png',
#              'lat': 37.4419,
#              'lng': -122.1419,
#              'infobox': "<b>Hello World</b>"
#           },
#           {
#              'icon': 'http://maps.google.com/mapfiles/ms/icons/blue-dot.png',
#              'lat': 37.4300,
#              'lng': -122.1400,
#              'infobox': "<b>Hello World from other place</b>"
#           }
#         ]
#     )
#     return render_template('example.html', mymap=mymap, sndmap=sndmap)


# @app.route("/polyline")
# def polyline_view():
#     polyline = {
#         "stroke_color": "#0AB0DE",
#         "stroke_opacity": 1.0,
#         "stroke_weight": 3,
#         "path": [
#             {"lat": 33.678, "lng": -116.243},
#             {"lat": 33.679, "lng": -116.244},
#             {"lat": 33.680, "lng": -116.250},
#             {"lat": 33.681, "lng": -116.239},
#             {"lat": 33.678, "lng": -116.243},
#         ],
#     }

#     path1 = [
#         (33.665, -116.235),
#         (33.666, -116.256),
#         (33.667, -116.250),
#         (33.668, -116.229),
#     ]

#     path2 = (
#         (33.659, -116.243),
#         (33.660, -116.244),
#         (33.649, -116.250),
#         (33.644, -116.239),
#     )

#     path3 = (
#         [33.688, -116.243],
#         [33.680, -116.244],
#         [33.682, -116.250],
#         [33.690, -116.239],
#     )

#     path4 = [
#         [33.690, -116.243],
#         [33.691, -116.244],
#         [33.692, -116.250],
#         [33.693, -116.239],
#     ]

#     plinemap = Map(
#         identifier="plinemap",
#         varname="plinemap",
#         lat=33.678,
#         lng=-116.243,
#         polylines=[polyline, path1, path2, path3, path4],
#     )

#     return render_template('example.html', mymap=plinemap, sndmap=plinemap)
