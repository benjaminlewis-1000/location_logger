#! /usr/bin/env python

# Resolves each historical_points row to a county (point-in-polygon lookup,
# same idiom CountyAdder._look_up_county uses in add_county_visits.py) and
# writes into county_visits -- deliberately much simpler than that file's
# CountyAdder: no speed filtering (these points have no real timestamps to
# filter on in the first place) and no frequent-county bbox shortcut (this
# is a one-time batch over a small, fixed set of trips, not a huge
# continuously-growing live-tracking dataset, so that optimization isn't
# worth the complexity here).
#
# Cross-validation: a county with zero corroboration anywhere else in the
# DB (counties.visited == False) is withheld rather than written straight
# to county_visits -- printed in a flagged summary for manual review
# instead. This exists because some of these GPX files were *recreated*
# rather than recovered originals, and a recreated route could plausibly
# clip a county that was never actually visited. Approving a flagged
# county is a manual follow-up (a targeted record_county_visit_year call,
# same pattern used for the Kane/Blackford/Glacier/Atlantic County check
# earlier) -- once approved, it shows up as corroborated on the next run
# and stops being flagged, with no separate approved-list bookkeeping.
#
# Safe to re-run: point-in-polygon lookups are skipped for already-
# computed points, and the county_visits write (record_county_visit_year)
# is select-then-insert-if-absent.

import re

import geopandas as gpd
from shapely.geometry import Point

import config
import location_db

database = location_db.locationDB(db_name=config.database_location,
        fips_file=config.county_fips_file,
        country_file=config.country_file)

geoData = gpd.read_file(config.basic_county_json)


def look_up_county(lat, lon):
    qpt = Point(float(lon), float(lat))
    in_county = geoData[geoData['geometry'].contains(qpt)]
    if len(in_county) == 0:
        return None
    # Normalized to the same 5-char fips counties.fips/county_visits.fips
    # use (GEO_ID is the longer Census format, e.g. '0500000US39113') --
    # done here, once, rather than deferred to record_county_visit_year
    # like the rest of the pipeline does, since this value gets persisted
    # into historical_points.fips and needs to already match that format
    # for the corroboration lookup against counties.fips to work at all.
    fips = str(in_county['GEO_ID'].item())
    if len(fips) != 5:
        fips = re.sub('.*US', '', fips)
    return fips


def compute_missing_fips():
    unprocessed = database.get_unprocessed_historical_points_dataframe()
    if len(unprocessed) == 0:
        print("No unprocessed points.")
        return

    print(f"Computing counties for {len(unprocessed)} unprocessed points...")
    updates = []
    last_fips = None
    last_source_file = None
    for row in unprocessed.itertuples():
        # Short-circuit: consecutive points along the same trip are very
        # often still in the same county -- skip the fresh polygon lookup
        # when the previous point (in the same file) already resolved
        # here. Not a hard guarantee of correctness (a point could
        # re-enter a previously-visited county after leaving it), just a
        # cheap check worth doing before the full lookup, same spirit as
        # replay_counties' last_county tracking.
        if row.source_file == last_source_file and last_fips is not None:
            qpt = Point(float(row.longitude), float(row.latitude))
            if geoData.loc[geoData['GEO_ID'] == last_fips, 'geometry'].contains(qpt).any():
                fips = last_fips
            else:
                fips = look_up_county(row.latitude, row.longitude)
        else:
            fips = look_up_county(row.latitude, row.longitude)

        updates.append({'id': row.id, 'fips': fips})
        last_fips = fips
        last_source_file = row.source_file

        if len(updates) >= 5000:
            database.set_historical_points_fips_batch(updates)
            updates = []

    database.set_historical_points_fips_batch(updates)
    print("Done computing counties.")


def commit_and_report():
    file_county_years = database.get_historical_county_file_sets()

    by_file = {}
    for source_file, fips, year in file_county_years:
        by_file.setdefault(source_file, []).append((fips, year))

    committed = []
    flagged = []
    for source_file, fips_years in sorted(by_file.items()):
        for fips, year in fips_years:
            status = database.get_county_status(fips)
            if status is None:
                continue
            if database.has_any_county_evidence(fips):
                database.record_county_visit_year(fips, year)
                committed.append((source_file, status['name'], status['state'], fips, year))
            else:
                flagged.append((source_file, status['name'], status['state'], fips, year))

    print(f"\nCommitted {len(committed)} (file, county) pairs (already corroborated):")
    for source_file, name, state, fips, year in committed:
        print(f"  {source_file}: {name}, {state} ({fips}) -- {year}")

    print(f"\nFlagged {len(flagged)} (file, county) pairs (NOT written -- no corroboration elsewhere):")
    for source_file, name, state, fips, year in flagged:
        print(f"  {source_file}: {name}, {state} ({fips}) -- {year}")
    if flagged:
        print("\nReview the flagged list above. To approve one, run:")
        print("  database.record_county_visit_year(fips, year)")


def main():
    compute_missing_fips()
    commit_and_report()


if __name__ == "__main__":
    main()
