
from calendar import timegm
from datetime import datetime, timedelta
from flask import Flask, request, Response, session, redirect, render_template, request, abort, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float
from sqlalchemy.sql import select
import dateutil
import dateutil.parser
import flask
import geocoder
import json
import jsonpickle
import math
import os
import random
import re
import requests
import sqlalchemy
import time
import csv
import urllib

import add_vals_quick as avq


engine = create_engine('sqlite:////data/location.sqlite', echo=False)


conn = engine.connect()

metadata = MetaData()
users = Table('users', metadata,
        Column('id', Integer, primary_key=True),
        Column('dev_id', String),
    )

positions = Table('positions', metadata,
        Column('id', Integer, primary_key=True),
        Column('date', DateTime),
        Column('utc_time', Float, index=True),
        Column('user_id', None, ForeignKey('users.id')),
        Column('latitude', Float),
        Column('longitude', Float),
        Column('altitude', Float),
        Column('battery', Integer),
        Column('accuracy', Float),
        Column('speed', Float),
        Column('source', String)
    )

metadata.create_all(engine)

file = 'AA704_2e1f4d6b.csv'
file = 'AA705_2e31c4e9.csv'
file = 'AA5285_2e1e8e1b.csv'
file = 'AA5968_2e33845b.csv'

uuid = avq.get_user_id('ben')
print(uuid)
with open(file, newline='') as cvsfile:
    data = csv.reader(cvsfile, delimiter=",")
    for row in data:
        if row[0] == 'Timestamp':
            continue
        print(row)

        try:
            date_data = datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            date_data = datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%SZ")

        print(date_data)

        pos_data = {}
        pos_data['uuid'] = uuid
        pos_data['dev_id'] = 'ben'
        pos_data['utc'] = int(row[0])
        pos_data['lat'] = row[3].split(',')[0]
        pos_data['lon'] = row[3].split(',')[1]
        pos_data['battery'] = -1
        pos_data['accuracy'] = -1
        pos_data['date'] = date_data
        pos_data['altitude'] = 0
        pos_data['speed'] = 0
        pos_data['source'] = 'hist'

        print(pos_data)
        try:
            avq.add_to_db(pos_data)
        except Exception as e:
            print(e)
        # exit()