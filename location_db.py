from sqlalchemy import create_engine, text
import re
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.sql import select
import sqlalchemy
import csv
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float, Boolean
import pandas as pd
import math
import numpy as np
from datetime import datetime
import dateutil.parser
import dateutil

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
                Column('year', Integer)
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
                sql_insert = 'alter table positions add column county_processed Boolean default False'
                with self.engine.begin() as conn2:
                    result = conn2.execute(text(sql_insert)) 
                    conn2.commit()
                    
            columns = insp.get_columns('counties')
            cnames = [c['name'] for c in columns]
            if 'year' not in cnames:
                sql_insert = 'alter table counties add column year Integer default -1'
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

    def populate_county_table(self):

        # create_database(self.engine.url)

        print("Populate")

        for ln in range(len(self.fips)):
            line = self.fips.iloc[ln]
            if type(line.state) is str:
                mkcounty = self.counties.insert().values(fips=line.fips,name=line.name,state=line.state,visited=False)
                r = self.conn.execute(mkcounty)
        self.conn.commit()

    def set_visited_county(self, county_year_tuple: tuple):
        # Check that the fips is in the table

        assert type(county_year_tuple) == tuple
        assert len(county_year_tuple) == 2
        county_fips, year = county_year_tuple
        assert type(county_fips) == str
        assert type(year) == int

        if len(county_fips) != 5:
            county_fips = re.sub('.*US', '', county_fips)
        assert len(county_fips) == 5

        fips_statement = self.counties.c.fips == county_fips
        exists = select(self.counties.c).where(fips_statement)
        result = self.conn.execute(exists)
        data = result.fetchall()
        assert len(data) == 1
        print(data)

        # Set the data
        county_update = self.counties.update().where(fips_statement).values(visited=True, year=year)
        self.conn.execute(county_update)
        self.conn.commit()

    def set_visited_multiple_counties(self, county_fips_ids: list):
        # Check that the fips is in the table
        raise NotImplementedError("Need to update")

        fips_statement = self.counties.c.fips.in_(tuple(county_fips_ids))
        exists = select(self.counties.c).where(fips_statement)
        result = self.conn.execute(exists)
        data = result.fetchall()
        assert len(data) == len(county_fips_ids)

        # # Set the data
        county_update = self.counties.update().where(fips_statement).values(visited=True)
        self.conn.execute(county_update)

    def unset_all_points(self):
        query = self.positions.update() \
                    .values(county_processed = False)
        self.conn.execute(query)
        self.conn.commit()

    def set_point_county_processed(self, position_id: int):
        # Set the value of 'county_processed' in the positions 
        # table for a point with position_id
        assert type(position_id) in [int, np.int32, np.int64]
        position_id = int(position_id)
        print(position_id, type(position_id))

        exists = select(self.positions.c.id).where(self.positions.c.id == position_id )
        result = self.conn.execute(exists)
        data = result.fetchall()
        print(data[-10:])

        query = self.positions.update() \
            .where(self.positions.c.id == position_id) \
            .values(county_processed = True)
        self.conn.execute(query)
        self.conn.commit()


    def get_num_visited(self):
        visited = select(self.counties.c).where(self.counties.c.visited == True)
        result = self.conn.execute(visited)
        result = result.fetchall()
        return len(result)


    def get_user_id(self, name):
        user_q = select(self.users.c.id).where(self.users.c.dev_id == name)
        user_res = self.conn.execute(user_q)
        
        user_id = user_res.fetchone()
        if user_id == None:
            user_ins = self.users.insert().values(dev_id=name)
            result = self.conn.execute(user_ins)
            user_id = result.inserted_primary_key[0]
            self.conn.commit()
        else:
            user_id = user_id[0]

        return user_id

    def delete_point(self, location_vals: dict):

        assert 'start_date' in location_vals
        assert 'end_date' in location_vals
        assert 'lat_top' in location_vals
        assert 'lat_bot' in location_vals
        assert 'lon_left' in location_vals
        assert 'lon_right' in location_vals
            
        sval = location_vals['start_date']
        start, specific_start = calc_start( location_vals['start_date'], default_start='now')
        end, specific_end = calc_end(location_vals['end_date'])

        start_utc = int(start.strftime('%s'))
        end_utc = int(end.strftime('%s'))
        lat_top = float(location_vals['lat_top'])
        lat_bot = float(location_vals['lat_bot'])
        lon_left = float(location_vals['lon_left'])
        lon_right = float(location_vals['lon_right'])

        if specific_start:
            start_datetime = start.strftime('%Y-%m-%d %H:%M:%S')
        else:
            start_datetime = start.strftime('%Y-%m-%d')
        if specific_end:
            end_datetime = start.strftime('%Y-%m-%d %H:%M:%S')
        else:
            end_datetime = end.strftime('%Y-%m-%d')

        
        pc = self.positions.c
        d_query = self.positions.delete().where(pc.utc_time >= start_utc)\
            .where(pc.utc_time <= end_utc)\
            .where(pc.latitude >= lat_bot)\
            .where(pc.latitude <= lat_top)\
            .where(pc.longitude >= lon_left)\
            .where(pc.longitude <= lon_right)

        self.conn.execute(d_query)
        self.conn.commit()

    def delete_by_id(self, data_id: int):

        
        assert type(data_id) in [int, np.int32, np.int64]
        data_id = int(data_id)

        pc = self.positions.c
        d_query = self.positions.delete().where(pc.id == data_id)

        self.conn.execute(d_query)
        self.conn.commit()

    def retrieve_points(self, start_utc: int, end_utc: int):
        
        pc = self.positions.c
        pos_qry = select(pc.id, pc.date, pc.utc_time, pc.latitude, pc.longitude)\
            .where(pc.utc_time >= start_utc)\
            .where(pc.utc_time <= end_utc)\
            .order_by(pc.utc_time.asc())
        data = self.conn.execute(pos_qry)

        data = data.fetchall()
        data = pd.DataFrame(data, columns=['id', 'datetime', 'utc', 'lat', 'lon'])

        return data

    def retrieve_all_data(self):
        pc = self.positions.c

        all_qry = select(pc.id, pc.date, pc.utc_time, pc.latitude, pc.longitude, pc.county_processed)\
            .order_by(pc.utc_time.asc())
        data = self.conn.execute(all_qry)

        data = data.fetchall()
        data = pd.DataFrame(data, columns=['id', 'datetime', 'utc', 'lat', 'lon', 'county_proc'])

        return data

    def insert_location(self, location_dict: dict):

        user_id = self.get_user_id(location_dict['dev_id'])

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

if __name__ == "__main__":

    item = locationDB(db_name = 'location2.sqlite', fips_file = 'config_files/state_and_county_fips_master.csv')
    # Get number of populated counties
    print(item.get_num_visited())
    # item.set_visited_county('37113')
    # item.set_visited_multiple_counties(['37113', '37111', '37101'])
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

    print(item.insert_location(pos_data))
    data = item.retrieve_points(start_utc = ts-1, end_utc = ts+1)
    print(data)
    item.delete_by_id(1)
    data = item.retrieve_points(start_utc = ts-1, end_utc = ts+1)
    print(data)

    item.insert_location(pos_data)
    pos_data['utc'] = ts + 1
    item.insert_location(pos_data)
    print(item.retrieve_points(start_utc = ts-1, end_utc = ts+10))

    # import requests

    # response = requests.post("https://owntracks.exploretheworld.tech/log", 
    #     data="lat=0&lon=0&timestamp=0&acc=9999&spd=5")
    # print(response, dir(response))
    # print(response.text)