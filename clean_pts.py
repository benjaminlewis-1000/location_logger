#! /usr/bin/env python

import flask
import numpy as np

from flask import Flask, request, Response, session, redirect, render_template, request, abort, jsonify
from flask_cors import CORS, cross_origin
from flask_session import Session
import jsonpickle
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float
from sqlalchemy import create_engine, and_
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
import dateutil.parser
import test_flask

conn = test_flask.conn
users = test_flask.users
positions = test_flask.positions

ll_pairs = [
    # (2015, 23.74,  -162.0,  16.8,   -152.8,),
    # (2015,41.839, -110.207, 41.02,  -108.92, ),
    # (2015, 32.993, -96.956, 32.916,  -96.835,),
    # (2015, 31.323, -117.328, 32.993, -118.468, ),
    # (2015, 37.61, -94.44, 0, 0, ),
    # (2015, 41.93, -81.55, 0, 0, ),
    # (2015, 39.883, -105.017, 39.64, -104.798 ),
    # (2015, 89, -87.91, 41.25, 0 ),
    # (2015, 33.852, -116.99, 33.67, -116.806 ),
    # (2015, 34.2322, -118.411, 34.225, -118.401 ),
    # (2016, 24.4, -163.4, 15.78, -151.3 ),
    # (2016, 35.5, -121.3, 32.8, -114.3 ),
    # (2016, 36.6, -94.3, 0, 0 ),
    # (2016, 37.59, -122.35, 37.47, -122.20  ),
    # (2016, 39.88, -105.27, 39.2, -104.11  ),
    # (2016, 34.5, -113.7, 31.7, -109.8),
    # (2016, 40.8, -73.9, 0, 0),
    # (2017, 41.8, -86.6, 41.3, -85.7),
    # (2017, 40.6, -111.6, 40.3, -111.13),
    # (2018, 36, 58, 0, 180),
    # (2018, 37.1, -76.7, 0, 0),
    ]

for ltup in ll_pairs:
    utc_start = (ltup[0] - 1970) * 3600 * 24 * 365.25
    utc_stop = (ltup[0] + 1 - 1970) * 3600 * 24 * 365.25

    andval = and_(
                  positions.c.latitude > ltup[3],
                 positions.c.longitude < ltup[4],
                 positions.c.latitude < ltup[1],
                 positions.c.longitude > ltup[2],
                 positions.c.utc_time > utc_start,
                 positions.c.utc_time < utc_stop,
                 )
    user_q = select([positions.c.id]).where(andval)
    user_res = conn.execute(user_q)

    a = user_res.fetchall()
    print(len(a))

    d_query = positions.delete().where(andval)
    conn.execute(d_query)