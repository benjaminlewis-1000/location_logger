#! /usr/bin/env python

# Historical GPX trips (pre-GPS-logging-era, exported from old devices)
# whose timestamps aren't trustworthy for real use -- only the calendar
# year of each trip is known (see the files list below). Rather than
# add_historical_counties.py's old approach of computing county
# membership directly from the GPX points and discarding the points
# themselves, this inserts every point as a genuine `positions` row (like
# any other GPS source) with a *synthesized* timestamp, so the raw data
# is never lost and the standard county-visit pipeline (add_county_visits.py
# / backfill_county_visit_years.py) picks these up automatically -- no
# special-casing needed.
#
# Synthesis: within a trip, each point's timestamp is the previous
# point's plus (distance to this point / SYNTHETIC_SPEED_MPS) -- a
# deliberately low, conservative assumed speed so these points never
# trip add_county_visits.py's 45 m/s flyover filter. Trips within the
# same year are spaced TRIP_SPACING_DAYS apart starting 1/1 of that
# year, so different trips' synthesized timelines can never overlap
# (checked against the actual manifest below: the busiest year has at
# most a handful of trips, nowhere close to overflowing a year at this
# spacing).
#
# Run manually (not via cron) once the source GPX files are in place
# under root_dir -- dev first, then prod, per CLAUDE.md's rollout notes.

import os
from collections import defaultdict
from datetime import datetime, timedelta

import gpxpy
import geopy.distance

import config
import location_db

database = location_db.locationDB(db_name=config.database_location,
        fips_file=config.county_fips_file,
        country_file=config.country_file)

root_dir = '/project/Downloads/historical_gpx'

SYNTHETIC_SPEED_MPS = 10.0   # ~22mph -- well under add_county_visits.py's 45 m/s flyover filter
TRIP_SPACING_DAYS = 10

# Same manifest as add_historical_counties.py's `files` list -- copy
# entries here (uncommented) once the archive is restored to root_dir.
files = [
#        ('boulder.gpx', 2015),
#         ('pvu_abq1.gpx', 2014),
#         ('boise_seattle.gpx', 2011),
#         ('boseman_yellowstone.gpx', 2013),
#         ('boston_p3.gpx', 2005),
#         ('boston_p4.gpx', 2005),
#         ('carlsbad.gpx', 2014),
#         ('conference_nm.gpx', 2014),
#         ('co_ward_camp.gpx', 2014),
#         ('dallas2.gpx', 2005),
#         ('dallas.gpx', 2005),
#         ('lagrande_spokane.gpx', 2013),
#         ('muir_woods.gpx', 2012),
#         ('nauvoo.gpx', 2004),
#         ('nm_camping.gpx', 2014),
#         ('okc.gpx', 2005),
#         ('ok_to_70.gpx', 2005),
#         ('orlando_1.gpx', 2002),
#         ('orlando_2.gpx', 2002),
#         ('orlando_3.gpx', 2002),
#         ('reno_sf.gpx', 2012),
#         ('pvu_abq2.gpx', 2014),
#         ('pvu_reno.gpx', 2012),
#         ('pvu_lagrande.gpx', 2013),
#         ('rexburg_provo.gpx', 2013),
#         ('salt_plains.gpx', 2004),
#         ('scout_reservation.gpx', 2003),
#         ('sea_vancouver.gpx', 2011),
#         ('spokane_boseman.gpx', 2013),
#         ('stillater_hale.gpx', 2005),
#         ('to_boston_p1.gpx', 2005),
#         ('to_boston_p2.gpx', 2005),
#         ('to_branson.gpx', 2004),
#         ('trip_to_park_ca.gpx', 2012),
#         ('tuscon.gpx', 2014),
#        ('to_chicago_2016.gpx', 2016),
#        ('to_palmyra.gpx', 2017),
#        ('raleigh_1.gpx', 2017),
#        ('raleigh_2.gpx', 2017),
#        ('raleigh_4.gpx', 2017),
#        ('raleigh_3.gpx', 2017),
#        ('nick_trip.gpx', 2014),
        # ('sharon_vt.gpx', 2005),
        # ('story_land.gpx', 2005)
        ]


def load_points(fname):
    # Flattened across all tracks/segments (matching
    # addpoints_gpx_google.py's more general iteration), rather than
    # add_historical_counties.py's single-track/segment assumption.
    path = os.path.join(root_dir, fname)
    with open(path, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            points.extend(segment.points)
    return points


def synthesize_trip_timestamps(points, start_time):
    timestamps = [start_time]
    for prev, curr in zip(points, points[1:]):
        dist_m = geopy.distance.geodesic(
                (prev.latitude, prev.longitude), (curr.latitude, curr.longitude)).m
        gap = timedelta(seconds=dist_m / SYNTHETIC_SPEED_MPS)
        timestamps.append(timestamps[-1] + gap)
    return timestamps


def insert_trip(fname, points, timestamps):
    for point, ts in zip(points, timestamps):
        pos_data = {}
        pos_data['dev_id'] = 'ben'
        pos_data['utc'] = ts.timestamp()
        pos_data['date'] = ts
        pos_data['lat'] = point.latitude
        pos_data['lon'] = point.longitude
        pos_data['battery'] = -1
        pos_data['accuracy'] = -1
        pos_data['altitude'] = point.elevation if point.elevation is not None else -100
        pos_data['speed'] = 0
        pos_data['source'] = 'synthetic_hist'
        database.insert_location(pos_data)


def main():
    trips_by_year = defaultdict(list)
    for fname, year in files:
        trips_by_year[year].append(fname)

    for year, fnames in trips_by_year.items():
        for trip_index, fname in enumerate(fnames):
            start_time = datetime(year, 1, 1) + timedelta(days=trip_index * TRIP_SPACING_DAYS)
            points = load_points(fname)
            if not points:
                print(f"No points found in {fname}, skipping")
                continue

            timestamps = synthesize_trip_timestamps(points, start_time)

            span = timestamps[-1] - timestamps[0]
            if span >= timedelta(days=TRIP_SPACING_DAYS):
                raise AssertionError(
                        f"{fname} ({year}): synthesized span {span} reaches into the next "
                        f"trip's start (spacing is {TRIP_SPACING_DAYS} days) -- lower "
                        f"SYNTHETIC_SPEED_MPS for this trip or widen TRIP_SPACING_DAYS "
                        f"rather than let two trips' points overlap.")

            print(f"{fname}: {len(points)} points, {start_time.date()} -> {timestamps[-1].date()}")
            insert_trip(fname, points, timestamps)


if __name__ == "__main__":
    main()
