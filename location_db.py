#! /usr/bin/env python

from datetime import datetime
from sqlalchemy import create_engine, text, func, or_
from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.sql import select
from sqlalchemy_utils import database_exists, create_database
import csv
import dateutil
import dateutil.parser
import math
import numpy as np
import pandas as pd
import re
import sqlalchemy
import time

class locationDB:
    """Wraps the SQLite DB (positions/users/counties/countries).

    Standing rule: dev's DB is a one-time clone of prod's and has
    been fully independent ever since -- nothing done to it here ever
    reaches prod, including by merging code. Any schema change must
    self-migrate on every startup (see the ALTER TABLE / populate_*
    checks in __init__ below) rather than assume a new column/table
    already exists -- prod will still be on the old schema whenever
    this code actually reaches it.
    """
    def __init__(self, db_name, fips_file, country_file):
        super(locationDB, self).__init__()
        self.db_name = db_name

        self.fips = pd.read_csv(fips_file)
        # keep_default_na=False: pandas' default NA-sentinel list
        # includes the literal string "NA", which is Namibia's actual
        # ISO alpha-2 code -- without this it silently reads as a
        # missing value instead of the string "NA".
        self.countries = pd.read_csv(country_file, keep_default_na=False)
        # Convert the fips column to a string with leading zeros
        self.fips.fips = self.fips.fips.astype(str).str.zfill(5)

        self.engine = create_engine(f"sqlite:///{db_name}", echo=False, future=True) 
        self.conn = self.engine.connect()
        # self.conn.execution_options(preserve_rowcount=True)
        
        metadata = MetaData()
        self.us_counties = Table('counties', metadata,
                Column('fips', String, primary_key=True),
                Column('name', String),
                Column('state', String),
                Column('visited', Boolean),
                Column('year', Integer)
            )

        self.world_countries = Table('countries', metadata,
                Column('name', String),
                Column('code_2', String),
                Column('code_3', String),
                Column('visited', Boolean),
                Column('flown_through', Boolean, default=False),
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
                # self.us_counties.create(self.conn.bind)
                metadata.create_all(self.engine)

            exist_cn=insp.has_table("countries")
            if not exist_cn: # set(insp.get_table_names()) == set(['users', 'positions']):
                print("Need to add country table")
                # self.us_counties.create(self.conn.bind)
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

            # Any DB that pre-dates this column (i.e. every DB except
            # a brand new one created fresh via the Table def above)
            # needs it added by hand -- see the standing rule in this
            # class's docstring.
            columns = insp.get_columns('countries')
            cnames = [c['name'] for c in columns]
            if 'flown_through' not in cnames:
                sql_insert = 'alter table countries add column flown_through Boolean default False'
                with self.engine.begin() as conn2:
                    result = conn2.execute(text(sql_insert))
                    conn2.commit()

        insp = sqlalchemy.inspect(self.engine)

        # See if the counties table is populated
        counties_pop = select(self.us_counties.c)
        result = self.conn.execute(counties_pop)
        result = result.fetchall()
        if len(result) == 0:
            self.populate_county_table()

        # See if the countries table is populated
        country_pop = select(self.world_countries.c)
        result = self.conn.execute(country_pop)
        result = result.fetchall()

        if len(result) == 0:
            self.populate_countries()

        # Repair a pre-existing data bug: pandas' default NA-sentinel
        # list includes the literal string "NA" -- which is Namibia's
        # real ISO alpha-2 code -- so any DB seeded before
        # keep_default_na=False (see self.countries above) got NULL
        # code_2/code_3 for it instead. Self-heals on every startup;
        # a no-op once fixed, and general (not hardcoded to Namibia)
        # in case another code collides with a pandas NA sentinel.
        broken = select(self.world_countries.c.name).where(
                or_(self.world_countries.c.code_2 == None, self.world_countries.c.code_3 == None))
        broken_names = [row[0] for row in self.conn.execute(broken).fetchall()]
        if broken_names:
            lookup = self.countries.set_index('name')
            for name in broken_names:
                if name not in lookup.index:
                    continue
                fix = self.world_countries.update() \
                        .where(self.world_countries.c.name == name) \
                        .values(code_2=lookup.loc[name, 'alpha-2'], code_3=lookup.loc[name, 'alpha-3'])
                self.conn.execute(fix)
            self.conn.commit()

    def get_visited_countries(self):

        exists = select(self.world_countries).where(self.world_countries.c.visited == True)
        result = self.conn.execute(exists)
        data = result.fetchall()

        df = pd.DataFrame(data, columns=['name', 'iso_2', 'iso_3', 'visited'])

        return df

    def get_all_countries_dataframe(self):
        # Same shape as get_visited_countries(), but every row (needed
        # to render the world choropleth, which colors visited vs.
        # unvisited rather than just plotting a list of visited names).
        all_countries = select(self.world_countries)
        result = self.conn.execute(all_countries)
        data = result.fetchall()

        df = pd.DataFrame(data, columns=['name', 'iso_2', 'iso_3', 'visited', 'flown_through'])

        return df

    def _find_country_row(self, identifier):
        # ID can be name, 2-char code, or 3-char code. Shared by every
        # method below that needs to locate a country row before
        # reading or updating it -- returns (row_or_None, where_clause)
        # so callers that go on to update can reuse the same clause
        # rather than re-deriving it.
        where_clause = or_(self.world_countries.c.name == identifier,
                        self.world_countries.c.code_2 == identifier,
                        self.world_countries.c.code_3 == identifier)

        find_country = select(self.world_countries).where(where_clause)
        results = self.conn.execute(find_country).fetchall()
        if len(results) == 0:
            return None, where_clause

        return results[0], where_clause

    def get_country_status(self, identifier):
        # Current visited/flown_through state for one country, or None
        # if the identifier doesn't match anything. Used by /log_country
        # to tell whether a submission is a genuine change (worth
        # letting the client undo) or a no-op resubmit of something
        # already set (not -- undoing that could clear a fact that's
        # actually true from an untracked, possibly much older action).
        row, _ = self._find_country_row(identifier)
        if row is None:
            return None

        return {
            'name': row.name,
            'iso_2': row.code_2,
            'iso_3': row.code_3,
            'visited': bool(row.visited),
            'flown_through': bool(row.flown_through),
        }

    def set_visited_country(self, identifier):
        row, where_clause = self._find_country_row(identifier)
        if row is None:
            # Invalid identifier
            return False

        country_update = self.world_countries.update() \
                        .where(where_clause) \
                        .values(visited=True)

        self.conn.execute(country_update)
        self.conn.commit()

        return True

    def set_flown_through_country(self, identifier):
        # Same as set_visited_country, but for the weaker "flew over,
        # didn't visit" fact -- the two are independent columns (both
        # can be true), never cleared by one another. Display-time
        # code is responsible for treating visited as taking priority
        # when both are set, not this method.
        row, where_clause = self._find_country_row(identifier)
        if row is None:
            # Invalid identifier
            return False

        country_update = self.world_countries.update() \
                        .where(where_clause) \
                        .values(flown_through=True)

        self.conn.execute(country_update)
        self.conn.commit()

        return True

    def unset_visited_country(self, identifier):
        # Undo counterpart to set_visited_country. Like the setters,
        # this just forces the one column -- callers are responsible
        # for only calling it when that's actually the right thing to
        # undo (see get_country_status's docstring above).
        row, where_clause = self._find_country_row(identifier)
        if row is None:
            return False

        country_update = self.world_countries.update() \
                        .where(where_clause) \
                        .values(visited=False)

        self.conn.execute(country_update)
        self.conn.commit()

        return True

    def unset_flown_through_country(self, identifier):
        row, where_clause = self._find_country_row(identifier)
        if row is None:
            return False

        country_update = self.world_countries.update() \
                        .where(where_clause) \
                        .values(flown_through=False)

        self.conn.execute(country_update)
        self.conn.commit()

        return True

    def populate_countries(self):
        for ln in range(len(self.countries)):
            line = self.countries.iloc[ln]
            name = line['name']
            alpha_2 = line['alpha-2']
            alpha_3 = line['alpha-3']
            # print(name, alpha_2, alpha_3)

            if type(name) is str:
                mk_country = self.world_countries.insert().values(name=name, code_2 = alpha_2, code_3 = alpha_3, visited=False, flown_through=False)
                r = self.conn.execute(mk_country)
        self.conn.commit()

    def populate_county_table(self):

        # create_database(self.engine.url)

        print("Populate")

        for ln in range(len(self.fips)):
            line = self.fips.iloc[ln]
            if type(line.state) is str:
                mkcounty = self.us_counties.insert().values(fips=line.fips,name=line.name,state=line.state,visited=False)
                r = self.conn.execute(mkcounty)
        self.conn.commit()

    def count_unprocessed_counties(self):
        # Not sure I understand completely how
        # the count statement works, but it does. 
        query = select(self.positions).where(self.positions.c.county_processed == False)# .count() 
        count_stmt = select(func.count("*")).select_from(
            query.alias("s")
        )
        result = self.conn.execute(count_stmt).scalar()
        return result

    def set_visited_county(self, county_year_tuple: tuple):
        # Check that the fips is in the table

        assert type(county_year_tuple) == tuple
        assert len(county_year_tuple) == 2
        county_fips, update_year = county_year_tuple
        assert type(county_fips) == str
        assert type(update_year) == int

        if len(county_fips) != 5:
            county_fips = re.sub('.*US', '', county_fips)
        assert len(county_fips) == 5

        fips_statement = self.us_counties.c.fips == county_fips
        exists = select(self.us_counties.c.fips, self.us_counties.c.visited, self.us_counties.c.year).where(fips_statement)
        result = self.conn.execute(exists)
        data = result.fetchall()
        # print(data)
        assert len(data) == 1
        cfips, visited, visit_year = data[0]
        # print(data, visit_year, cfips, visited)

        if update_year <= visit_year and visited:
            # print("No update")
            pass
        else:
            # Set the data
            county_update = self.us_counties.update().where(fips_statement).values(visited=True, year=update_year)
            self.conn.execute(county_update)
            self.conn.commit()

    def set_visited_multiple_counties(self, county_fips_ids: list):
        # Check that the fips is in the table
        raise NotImplementedError("Need to update")

        fips_statement = self.us_counties.c.fips.in_(tuple(county_fips_ids))
        exists = select(self.us_counties.c).where(fips_statement)
        result = self.conn.execute(exists)
        data = result.fetchall()
        assert len(data) == len(county_fips_ids)

        # # Set the data
        county_update = self.us_counties.update().where(fips_statement).values(visited=True)
        self.conn.execute(county_update)
        self.conn.commit()

    def unset_all_points(self):
        query = self.positions.update() \
                    .values(county_processed = False)
        self.conn.execute(query)
        self.conn.commit()

        query_cty = self.us_counties.update() \
                    .values(visited = False, year=-1)
        self.conn.execute(query_cty)
        self.conn.commit()

    def unset_county_by_fips(self, fips: str):
        assert type(fips) == str

        fips_statement = self.us_counties.c.fips == fips
        county_update = self.us_counties.update().where(fips_statement).values(visited=False, year=-1)
        self.conn.execute(county_update)
        self.conn.commit()

    def set_point_county_processed(self, position_id: int):
        # Set the value of 'county_processed' in the positions 
        # table for a point with position_id
        assert type(position_id) in [int, np.int32, np.int64]
        position_id = int(position_id)

        exists = select(self.positions.c.id).where(self.positions.c.id == position_id )
        result = self.conn.execute(exists)
        data = result.fetchall()

        query = self.positions.update() \
            .where(self.positions.c.id == position_id) \
            .values(county_processed = True)
        self.conn.execute(query)
        self.conn.commit()

    def set_pointlist_county_processed(self, position_list: list):
        # Used to update points for frequently visited counties
        assert type(position_list) == list

        # Iterate over the list
        start_idx = 0
        num_per_iter = 5000
        for i in range(len(position_list) // num_per_iter + 1):
            start_idx = i * num_per_iter
            end_idx = (i + 1) * num_per_iter
            sublist = position_list[start_idx:end_idx]

            ids_update = self.positions.c.id.in_(tuple(sublist))

            update = self.positions.update() \
                .where(ids_update).values(county_processed=True)

            self.conn.execute(update)
            self.conn.commit()
            

    def get_num_counties_visited(self):
        visited = select(self.us_counties.c).where(self.us_counties.c.visited == True)
        result = self.conn.execute(visited)
        result = result.fetchall()
        return len(result)

    def get_last_visit_year(self):
        visited = select(self.us_counties.c.year).where(self.us_counties.c.visited == True)
        result = self.conn.execute(visited)
        result = result.fetchall()
        
        if result is None or len(result) == 0:
            return -1
        return int(np.max(result))

    def get_average_visit_year(self):
        visited = select(self.us_counties.c.year).where(self.us_counties.c.visited == True)
        result = self.conn.execute(visited)
        result = result.fetchall()
        
        if result is None or len(result) == 0:
            return -1

        result = np.array(result).reshape(-1)
        average_year = np.mean(result)
        
        return average_year

    def get_points_to_parse_dataframe(self, start_utc = None, num_points = None):

        pc = self.positions.c

        if num_points is not None:
            if type(num_points) is not int or num_points <= 0:
                raise ValueError("Num points must be a positive integer.")

        if start_utc is not None:
            min_unproc_qry = select(pc.utc_time) \
                .where(pc.county_processed == False) \
                .where(pc.utc_time > start_utc) \
                .order_by(pc.utc_time.asc())
        else:
            min_unproc_qry = select(pc.utc_time) \
                .where(pc.county_processed == False) \
                .order_by(pc.utc_time.asc())

        data = self.conn.execute(min_unproc_qry)
        
        min_unprocessed = data.fetchone()
        
        if min_unprocessed is None or len(min_unprocessed) == 0:
            return None
        else:
            min_unprocessed = min_unprocessed[0]

        # Then get the maximum utc time that's lower
        # than the minimum unprocessed value.
        max_cmp_qry = select(pc.utc_time) \
            .where(pc.utc_time < min_unprocessed) \
            .order_by(pc.utc_time.desc()).limit(5)

        data = self.conn.execute(max_cmp_qry)
        all_data = data.fetchall()
        if len(all_data) == 0:
            min_cmp = 0
            # max_cmp = 0
        else:
            min_cmp = np.min(all_data)

        # print('unproc/cmpr', min_unprocessed, min_cmp, min_unprocessed - min_cmp)
        assert min_cmp <= min_unprocessed

        # Query: All relevant data that is greater than that lower bound plus a few outliers.
        relevant_data_query = select(pc.id, pc.date, pc.utc_time, pc.latitude, pc.longitude, pc.county_processed, pc.accuracy) \
            .where(pc.utc_time >= min_cmp) \
            .order_by(pc.utc_time.asc())

        if num_points is not None:
            # Limit the amount of data.
            relevant_data_query = relevant_data_query.limit(num_points)
            
        data = self.conn.execute(relevant_data_query)

        data = data.fetchall()
        data = pd.DataFrame(data, columns=['id', 'datetime', 'utc', 'lat', 'lon', 'county_proc', 'accuracy'])

        return data


    def get_county_visits_dataframe(self):
        county_data = select(self.us_counties.c.fips, \
                             self.us_counties.c.visited, \
                             self.us_counties.c.state, \
                             self.us_counties.c.year)

        result = self.conn.execute(county_data)
        result = result.fetchall()
        result = pd.DataFrame(result, columns=['FIPS', 'visited', 'state', 'year'])
        # result.year = pd.to_numeric(result.year)

        pos_idcs = result['year'] > 0
        neg_idcs = result['year'] < 0
        base_year = 2000

        # print("PI", len(pos_idcs))
        num_positive = len(np.where(pos_idcs)[0])
        # print(len(num_true))
        # print(pos_idcs)

        if num_positive > 0:

            min_year = int(np.min(result[pos_idcs].year))
            max_year = int(np.max(result[pos_idcs].year))
            result.loc[pos_idcs, 'year'] = result['year'].apply(lambda x: x - base_year) # min_year + (max_year - min_year) // 4)

        return result

    def get_state_visits_dataframe(self):
        state_data = select(self.us_counties.c.state, self.us_counties.c.visited, self.us_counties.c.year)
        result = self.conn.execute(state_data)
        result = result.fetchall()
        result = pd.DataFrame(result, columns=['state', 'visited', 'year'])
        # Sort smallest to largest year
        result = result.sort_values(by='year')
        # Drop duplicates of states, keep the last column (e.g. the latest
        # year visited to that state.)
        # Easier to do in pandas than to try and get in SQL for me.
        result = result.drop_duplicates(subset=['state'], keep='last')

        # Same -2000 convention as get_county_visits_dataframe() (-1
        # stays -1 for "never visited"): callers rendering both
        # counties and states through the same year-slider JS need a
        # consistent offset, since that JS hardcodes YEAR_BASE = 2000.
        pos_idcs = result['year'] > 0
        if pos_idcs.any():
            result.loc[pos_idcs, 'year'] = result['year'].apply(lambda x: x - 2000)

        return result


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

        if re.match(r'\d+-\d+.?\d+ \d+.?\d+.?\d+', end_string):
            specific = True
        else:
            specific = False

        if re.match(r'^\d\d$', end_string) or re.match(r'^\d\d\d\d$', end_string):
            end_string = end_string + '-12-31'
        try:
            end = dateutil.parser.parse(end_string)
            if re.match(r'^\d\d.?\d\d$', end_string) or re.match(r'^\d\d\d\d.?\d\d$', end_string):
                end = end + dateutil.relativedelta.relativedelta(day=31)
            if not specific:
                end = end + dateutil.relativedelta.relativedelta(hour=23, minute=59, second=59)
        except:
            end = datetime.now()

        return end, specific


    def calc_start(self, start_string, default_start='now'):
        assert default_start in ['now', '1970']
        if re.match(r'^\d\d$', start_string) or re.match(r'^\d\d\d\d$', start_string):
            start_string = start_string + '-01-01'
        try:
            start = dateutil.parser.parse(start_string)
            if re.match(r'^\d\d.?\d\d$', start_string) or re.match(r'^\d\d\d\d.?\d\d$', start_string):
                start = start + dateutil.relativedelta.relativedelta(day=1)
        except:
            if default_start == '1970':
                start = dateutil.parser.parse('1970-1-1')
            else:
                start = datetime.now()
    
        if re.match(r'\d+-\d+.?\d+ \d+.?\d+.?\d+', start_string):
            specific = True
        else:
            specific = False

        return start, specific



    def get_debug_subset(self, min_time = 1721782342, max_time = 1721793142):

        pc = self.positions.c

        debug_qry = select(pc.id, pc.date, pc.utc_time, pc.latitude, pc.longitude, pc.county_processed) \
            .where(pc.utc_time >= min_time) \
            .where(pc.utc_time <= max_time) \
            .order_by(pc.utc_time.asc())
        data = self.conn.execute(debug_qry)

        data = data.fetchall()
        data = pd.DataFrame(data, columns=['id', 'datetime', 'utc', 'lat', 'lon', 'county_proc'])

        return data

if __name__ == "__main__":

    import config
    item = locationDB(db_name = 'location2.sqlite', fips_file = config.county_fips_file, country_file=config.country_file)
    # item = locationDB(db_name = config.database_location, fips_file = config.county_fips_file, country_file=config.country_file)
    # Get number of populated counties
    print(item.get_num_counties_visited())
    print(item.get_last_visit_year())
    # item.set_visited_county('37113')
    # item.set_visited_multiple_counties(['37113', '37111', '37101'])
    # print(item.get_num_visited())


    # ts = 1721917990
    # pos_data = {}
    # cur_datetime = datetime.utcfromtimestamp(int(ts))
    # pos_data['utc'] = ts
    # pos_data['lat'] = 0
    # pos_data['lon'] = 0
    # pos_data['battery'] = -1
    # pos_data['accuracy'] = 25
    # pos_data['date'] = cur_datetime
    # pos_data['dev_id'] = 'ben'
    # pos_data['speed'] = 0
    # pos_data['altitude'] = float(255)
        
    # pos_data['source'] = 'gps_logger'

    # print(item.insert_location(pos_data))
    # data = item.retrieve_points(start_utc = ts-1, end_utc = ts+1)
    # print(data)
    # item.delete_by_id(1)
    # data = item.retrieve_points(start_utc = ts-1, end_utc = ts+1)
    # print(data)

    # item.insert_location(pos_data)
    # pos_data['utc'] = ts + 1
    # item.insert_location(pos_data)
    # print(item.retrieve_points(start_utc = ts-1, end_utc = ts+10))

    # county_pair = ('0500000US13265', 2016)
    # county_pair2 = ('0500000US13265', 2012)
    # item.set_visited_county(county_pair)
    # item.set_visited_county(county_pair2)

    # dd = item.get_county_visits_dataframe()
    # result = item.get_state_visits_dataframe()
    # print(result)

    # print(item.get_num_counties_visited())

    # s = time.time()
    # # data = item.get_points_to_parse_dataframe(num_points=1203)
    # print(time.time() - s)

    debug = item.get_debug_subset()
    # import requests

    print("Unprocesseed")
    print(item.count_unprocessed_counties())
    s = time.time()
    print(item.get_average_visit_year())
    print(time.time() - s)

    print("1", item.set_visited_country('United States of America'))
    print("2", item.set_visited_country('United States a'))
    # item.set_visited_country('RS')
    # item.set_visited_country('PER')
    print(item.get_visited_countries())

    # response = requests.post("https://owntracks.exploretheworld.tech/log", 
    #     data="lat=0&lon=0&timestamp=0&acc=9999&spd=5")
    # print(response, dir(response))
    # print(response.text)
