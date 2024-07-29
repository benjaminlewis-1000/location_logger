from sqlalchemy import create_engine, text
import dateutil
import dateutil.parser
import re
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.sql import select
import sqlalchemy
import csv
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float, Boolean
import pandas as pd
import math
from datetime import datetime

class locationDB:
    """docstring for locationDB"""
    def __init__(self, db_name, fips_file):
        super(locationDB, self).__init__()
        self.db_name = db_name

        self.fips = pd.read_csv(fips_file)
        # Convert the fips column to a string with leading zeros
        self.fips.fips = self.fips.fips.astype(str).str.zfill(5)

        
        self.engine = create_engine(f"sqlite:///{db_name}", echo=False, future=True) 
        self.conn = self.engine.connect()
        
        metadata = MetaData()
        self.counties = Table('counties', metadata,
                Column('fips', String, primary_key=True),
                Column('name', String),
                Column('state', String),
                Column('visited', Boolean),
            )

        self.users = Table('users', metadata,
                Column('id', Integer, primary_key=True),
                Column('dev_id', String),
            )

        self.positions = Table('positions', metadata,
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
                Column('source', String),
                Column('county_processed', Boolean),
            )

        if not database_exists(self.engine.url):
            metadata.create_all(self.engine)        

        else:
            insp = sqlalchemy.inspect(self.engine)
            
            exist=insp.has_table("counties")
            if not exist: # set(insp.get_table_names()) == set(['users', 'positions']):
                print("Need to add table")
                # self.counties.create(self.conn.bind)
                metadata.create_all(self.engine)

            # Check that the table has a 'county_computed' field
            columns = insp.get_columns('positions')
            cnames = [c['name'] for c in columns]
            if 'county_processed' not in cnames:
                print("Newcol")
                sql_insert = 'alter table positions add column county_processed Boolean default False'
                with self.engine.begin() as conn2:
                    result = conn2.execute(text(sql_insert)) 
                    conn2.commit()

            
        insp = sqlalchemy.inspect(self.engine)

        # See if the counties table is populated
        counties_pop = select(self.counties.c)
        result = self.conn.execute(counties_pop)
        result = result.fetchall()
        if len(result) == 0:
            self.populate_county_table()

    def DataFrame(data)
        data.columns = ['datetime', 'utc', 'lat', 'lon']
        return data

    def calc_end(self, end_string, default_end='now'):

        assert default_end in ['now', '1970']

        if re.match('\d+-\d+.?\d+ \d+.?\d+.?\d+', end_string):
            specific = True
        else:
            specific = False

        if re.match('^\d\d$', end_string) or re.match('^\d\d\d\d$', end_string):
            end_string = end_string + '-12-31'
        try:
            end = dateutil.parser.parse(end_string)
            if re.match('^\d\d.?\d\d$', end_string) or re.match('^\d\d\d\d.?\d\d$', end_string):
                end = end + dateutil.relativedelta.relativedelta(day=31)
            if not specific:
                end = end + dateutil.relativedelta.relativedelta(hour=23, minute=59, second=59)
        except:
            end = datetime.now()

        return end, specific


    def calc_start(self, start_string, default_start='now'):
        assert default_start in ['now', '1970']
        if re.match('^\d\d$', start_string) or re.match('^\d\d\d\d$', start_string):
            start_string = start_string + '-01-01'
        try:
            start = dateutil.parser.parse(start_string)
            if re.match('^\d\d.?\d\d$', start_string) or re.match('^\d\d\d\d.?\d\d$', start_string):
                start = start + dateutil.relativedelta.relativedelta(day=1)
        except:
            if default_start == '1970':
                start = dateutil.parser.parse('1970-1-1')
            else:
                start = datetime.now()
    
        if re.match('\d+-\d+.?\d+ \d+.?\d+.?\d+', start_string):
            specific = True
        else:
            specific = False

        return start, specific

    def insert_location(self, location_dict: dict):

        user_id = self.get_user_id(location_dict['dev_id'])


        # s = select(self.positions.c.user_id)
        # r = self.conn.execute(s)
        

        # build a response dict to send back to client
        response = {'message': 'received'}

        # Occasionally, we get two post requests for the same datapoint. To avoid that, 
        # see if this UTC time is already in the database, and return if it is. 
        s = select(self.positions).where(self.positions.c.utc_time == location_dict['utc']) # .count()# 
        results = self.conn.execute(s)
        num_results = len(results.fetchall())

        if num_results == 0:
            
            alt = float(location_dict['altitude'])

            ins = self.positions.insert().values(date=location_dict['date'], utc_time=location_dict['utc'], latitude=location_dict['lat'], \
                longitude=location_dict['lon'], altitude=alt, battery=int(float(location_dict['battery'])), \
                accuracy=location_dict['accuracy'], speed=location_dict['speed'], user_id=user_id, source=location_dict['source'])
            # print(ins)
            result = self.conn.execute(ins)
            self.conn.commit()

            return {'message': 'logged'}

        return {'message': 'finished'}

if __name__ == "__main__":

    item = locationDB(db_name = 'location2.sqlite', fips_file = 'config_files/state_and_county_fips_master.csv')
    # Get number of populated counties
    print(item.get_num_visited())
    # item.set_visited('37113')
    # item.set_visited_multiple(['37113', '37111', '37101'])
    # print(item.get_num_visited())


    ts = 1721917990
    pos_data = {}
    cur_datetime = datetime.utcfromtimestamp(int(ts))
    pos_data['utc'] = ts
    pos_data['lat'] = 0
    pos_data['lon'] = 0
    pos_data['battery'] = -1
    pos_data['accuracy'] = 25
    pos_data['date'] = cur_datetime
    pos_data['dev_id'] = 'ben'
    pos_data['speed'] = 0
    pos_data['altitude'] = float(255)
    
    pos_data['source'] = 'gps_logger'

    # print(item.insert_location(pos_data))
    data = item.retrieve_points(start_utc = 1712128202, end_utc=1722128202)
    print(data)
