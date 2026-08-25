#! /usr/bin/env python

# Loads historical GPX trip points into their own `historical_points`
# table -- deliberately not `positions` (see process_historical_points.py
# for why: no intermingling with real device-logged GPS, and no need to
# synthesize a plausible timestamp, since this table's own processor
# doesn't run add_county_visits.py's speed-based flyover filter at all).
# Only the calendar year of each trip is known, which is all this table
# stores per point beyond raw lat/lon.
#
# Run manually (not via cron) once the source GPX files are in place
# under root_dir. Safe to re-run after adding new files to `files` below
# -- already-loaded files (by source_file) are skipped.

import os

import gpxpy

import config
import location_db

database = location_db.locationDB(db_name=config.database_location,
        fips_file=config.county_fips_file,
        country_file=config.country_file)

root_dir = '/project/Downloads/historical_gpx'

# Same (filename, year) pairs as add_historical_gpx_points.py's own
# manifest -- copied here rather than shared, since that script is
# superseded by this one. Deliberately excludes reno_sunnyvale.gpx
# (confirmed a duplicate export of reno_sf.gpx, same start/end points and
# point count) and the raleigh_3/raleigh_4 entries (consolidated by the
# user into raleigh_1.gpx/raleigh_2.gpx, not yet placed on disk).
files = [
        ('boulder.gpx', 2015),
        ('pvu_abq1.gpx', 2014),
        ('boise_seattle.gpx', 2011),
        ('boseman_yellowstone.gpx', 2013),
        ('boston_p3.gpx', 2005),
        ('boston_p4.gpx', 2005),
        ('carlsbad.gpx', 2014),
        ('conference_nm.gpx', 2014),
        ('co_ward_camp.gpx', 2014),
        ('dallas2.gpx', 2005),
        ('dallas.gpx', 2005),
        ('lagrande_spokane.gpx', 2013),
        ('muir_woods.gpx', 2012),
        ('nauvoo.gpx', 2004),
        ('nm_camping.gpx', 2014),
        ('okc.gpx', 2005),
        ('ok_to_70.gpx', 2005),
        ('orlando_1.gpx', 2002),
        ('orlando_2.gpx', 2002),
        ('orlando_3.gpx', 2002),
        ('reno_sf.gpx', 2012),
        ('pvu_abq2.gpx', 2014),
        ('pvu_reno.gpx', 2012),
        ('pvu_lagrande.gpx', 2013),
        ('rexburg_provo.gpx', 2013),
        ('salt_plains.gpx', 2004),
        ('scout_reservation.gpx', 2003),
        ('sea_vancouver.gpx', 2011),
        ('spokane_boseman.gpx', 2013),
        ('stillater_hale.gpx', 2005),
        ('to_boston_p1.gpx', 2005),
        ('to_boston_p2.gpx', 2005),
        ('to_branson.gpx', 2004),
        ('trip_to_park_ca.gpx', 2012),
        ('tuscon.gpx', 2014),
        ('to_chicago_2016.gpx', 2016),
        ('to_palmyra.gpx', 2017),
        ('raleigh_1.gpx', 2017),
        ('raleigh_2.gpx', 2017),
        ('nick_trip.gpx', 2014),
        ('sharon_vt.gpx', 2005),
        ('story_land.gpx', 2005),
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


def main():
    already_loaded = database.get_loaded_historical_source_files()

    for fname, year in files:
        if fname in already_loaded:
            print(f"{fname}: already loaded, skipping")
            continue

        points = load_points(fname)
        if not points:
            print(f"No points found in {fname}, skipping")
            continue

        rows = [{'source_file': fname, 'year': year,
                  'latitude': p.latitude, 'longitude': p.longitude} for p in points]
        database.insert_historical_points_batch(rows)
        print(f"{fname}: loaded {len(rows)} points ({year})")


if __name__ == "__main__":
    main()
