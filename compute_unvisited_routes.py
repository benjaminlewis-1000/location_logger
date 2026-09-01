#! /usr/bin/env python

"""Precomputes, once a day, a suggested loop through each scope's (state,
or the continental 'MAINLAND') currently-unvisited counties, plus a
one-time comparison tour through every county in the scope regardless of
visited status. Cached in location_db's unvisited_routes table and read
by serve_flask_interface.py's /state_view and /counties routes.

Distance is sourced primarily from config.usa3100_tsp_file (a real,
road-influenced distance matrix for the 3,100 continental+DC county
seats -- see CLAUDE.md for how its ordering was verified against
config.usa3100_locations_file and matched to our own FIPS codes), falling
back to a computed haversine (straight-line) distance between county
centroids for Alaska, Hawaii (structurally absent from that dataset), and
any county that fails to name-match.

Not invoked directly by cron -- see config_files/cronjob_tsp_routes.sh,
which wraps this in a dedicated flock (own lock file, separate from
add_county_visits.py's, since this only reads counties.visited and writes
an unrelated table -- no real contention with the ingestion pipeline).
"""

import json
import re
import sys
import time
import unicodedata

import numpy as np
import geopandas as gpd
from ortools.constraint_solver import routing_enums_pb2, pywrapcp

import config
import location_db

_METERS_PER_MILE = 1609.344
_EARTH_RADIUS_MILES = 3958.7613

# Daily unvisited-tour recompute budgets -- benchmarked for real against
# this app's actual data (see CLAUDE.md): the mainland scope (~3,100
# counties worst case) keeps improving meaningfully out to at least 570s,
# so it gets more room; every per-state scope converges within ~10s even
# for the largest state (Texas, 254 counties), so 300s is enormously
# generous, not a tight fit. Both are cheap regardless, since this only
# actually solves on a day that scope's unvisited set changed at all.
DAILY_TIME_LIMIT_MAINLAND_S = 900
DAILY_TIME_LIMIT_STATE_S = 300

# One-time full-scope comparison tour budget -- generous specifically
# because it only ever runs once per scope (see process_full_tour).
# Mainland gets extra time (the hardest full-tour instance, ~3,100
# counties, and -- like every full-tour computation -- only ever solved
# once) beyond the per-state budget.
FULL_TOUR_TIME_LIMIT_STATE_S = 600
FULL_TOUR_TIME_LIMIT_MAINLAND_S = 1200

MAINLAND_SCOPE = 'MAINLAND'

# Counties where Waterloo's label doesn't match our own name via simple
# normalization -- each hand-verified against the real usa3100_points.html
# data this session (see CLAUDE.md's "Full reconciliation" writeup), not
# guessed. Keyed by our own FIPS code, valued with the exact raw Waterloo
# "<city>, <county>, <ST>" (or "<city>, <ST>") label to look up directly.
SPECIAL_CASE_BY_FIPS = {
    # Consolidated city-counties -- worded completely differently from our
    # own county name ("San Francisco County" vs "City and County of San
    # Francisco"), not just a formatting variant.
    '06075': 'San Francisco, City and County of San Francisco, CA',
    '08014': 'Broomfield, City and County of Broomfield, CO',
    '08031': 'Denver, City and County of Denver, CO',
    # DC has no county segment in Waterloo's data at all.
    '11001': 'Washington, DC',
    # Spacing variant not caught by normalization (DeWitt vs De Witt).
    '17039': 'Clinton, DeWitt County, IL',
    # Our CSV's stored name has a corrupted/non-standard unicode
    # character for this county's actual "n with tilde" -- don't rely on
    # normalization for this one.
    '35013': 'Las Cruces, Dona Ana County, NM',
    # 2015 rename -- Waterloo used the new name, our CSV still has the old one.
    '46113': 'Oglala Lake, Oglala Lakota County, SD',
    # Virginia's 8 dual-role independent cities (also a neighboring
    # county's seat) plus Bedford (merged into Bedford County in 2013,
    # but our CSV still carries it as a separate row) -- each maps to the
    # SAME point as the county it seats, per the source page's own
    # "counted only once" design.
    '51540': 'Charlottesville, Albemarle County, VA',
    '51790': 'Staunton, Augusta County, VA',
    '51515': 'Bedford, Bedford County, VA',
    '51840': 'Winchester, Frederick County, VA',
    '51595': 'Emporia, Greensville County, VA',
    '51690': 'Martinsville, Henry County, VA',
    '51683': 'Manassas, Prince William County, VA',
    '51678': 'Lexington, Rockbridge County, VA',
    '51660': 'Harrisonburg, Rockingham County, VA',
}


def _normalize_name(s, apostrophe_as_space=False):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    s = s.lower().strip()
    s = s.replace('st.', 'saint').replace('ste.', 'sainte')
    if not apostrophe_as_space:
        # Strip apostrophes outright rather than letting the general
        # non-alnum substitution below turn them into a stray space --
        # "Prince George's County" needs to become "prince georges
        # county", matching Waterloo's own "Prince Georges County", not
        # "prince george s county". Waterloo isn't consistent about this
        # convention though -- "O'Brien County, IA" is spelled "O Brien
        # County" in their data (space, not stripped) -- so a caller
        # whose primary-normalized lookup misses should retry with
        # apostrophe_as_space=True before concluding there's no match.
        s = s.replace("'", '').replace('’', '')
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _lookup_name(state, name, county_label_index, city_index):
    for apostrophe_as_space in (False, True):
        if apostrophe_as_space and "'" not in name and '’' not in name:
            break  # no apostrophe in the name -- the retry can't differ
        norm_name = _normalize_name(name, apostrophe_as_space=apostrophe_as_space)
        idx = county_label_index.get((state, norm_name))
        if idx is None:
            idx = city_index.get((state, norm_name))
        if idx is not None:
            return idx
    return None


def load_county_centroids():
    with open(config.basic_county_json, 'rb') as f:
        counties_geojson = json.load(f)
    for feat in counties_geojson['features']:
        feat['properties']['GEO_ID'] = re.sub(r'0500000US', '', feat['properties']['GEO_ID'])
    gdf = gpd.GeoDataFrame.from_features(counties_geojson['features'])
    centroids = gdf.geometry.centroid
    return dict(zip(gdf['GEO_ID'], zip(centroids.y, centroids.x)))


def load_tsp_matrix(path):
    with open(path, 'r') as fh:
        lines = fh.readlines()
    dimension = None
    start_idx = None
    for i, line in enumerate(lines):
        data = line.strip()
        if data.startswith('DIMENSION'):
            dimension = int(data.split(':')[1].strip())
        elif data == 'EDGE_WEIGHT_SECTION':
            start_idx = i + 1
            break
    assert dimension is not None and start_idx is not None
    matrix = np.zeros((dimension, dimension), dtype=np.int64)
    row = 0
    for line in lines[start_idx:start_idx + dimension]:
        data = line.strip()
        if not data:
            continue
        matrix[row, :row + 1] = np.array(data.split(), dtype=np.int64)
        row += 1
    return matrix + matrix.T


def build_fips_to_matrix_index(county_df, waterloo_locations):
    raw_to_index = {raw: i for i, (raw, lat, lon) in enumerate(waterloo_locations)}
    county_label_index = {}
    city_index = {}
    for i, (raw, lat, lon) in enumerate(waterloo_locations):
        parts = [p.strip() for p in raw.split(',')]
        state = parts[-1]
        if len(parts) == 2:
            city_index[(state, _normalize_name(parts[0]))] = i
        else:
            county_label_index[(state, _normalize_name(parts[-2]))] = i

    fips_to_index = {}
    unmatched = []
    for fips, name, state in zip(county_df['FIPS'], county_df['name'], county_df['state']):
        special = SPECIAL_CASE_BY_FIPS.get(fips)
        if special is not None and special in raw_to_index:
            fips_to_index[fips] = raw_to_index[special]
            continue

        idx = _lookup_name(state, name, county_label_index, city_index)
        if idx is None and state == 'VA' and name.strip().lower().endswith('city'):
            base = re.sub(r'\s*city\s*$', '', name.strip(), flags=re.I)
            idx = city_index.get((state, _normalize_name(f'City of {base}')))

        if idx is not None:
            fips_to_index[fips] = idx
        else:
            unmatched.append((fips, name, state))
    return fips_to_index, unmatched


def _haversine_matrix_meters(lats, lons):
    lat_r = np.radians(lats)
    lon_r = np.radians(lons)
    dlat = lat_r[:, None] - lat_r[None, :]
    dlon = lon_r[:, None] - lon_r[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat_r[:, None]) * np.cos(lat_r[None, :]) * np.sin(dlon / 2) ** 2
    miles = 2 * _EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return miles * _METERS_PER_MILE


def build_distance_matrix(fips_list, fips_to_index, tsp_matrix, centroids_by_fips):
    lats = np.array([centroids_by_fips[f][0] for f in fips_list])
    lons = np.array([centroids_by_fips[f][1] for f in fips_list])
    dist = _haversine_matrix_meters(lats, lons)

    idx_arr = np.array([fips_to_index.get(f, -1) for f in fips_list])
    valid_positions = np.where(idx_arr >= 0)[0]
    if len(valid_positions) > 1:
        waterloo_indices = idx_arr[valid_positions]
        real_sub = tsp_matrix[np.ix_(waterloo_indices, waterloo_indices)]
        dist[np.ix_(valid_positions, valid_positions)] = real_sub

    np.fill_diagonal(dist, 0)
    return dist.astype(np.int64)


def solve_tour(dist_matrix, time_limit_s):
    n = dist_matrix.shape[0]
    if n <= 1:
        return list(range(n)), 0

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return int(dist_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)])

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(time_limit_s)

    solution = routing.SolveWithParameters(search_parameters)
    if solution is None:
        return None, None

    index = routing.Start(0)
    order = []
    total = 0
    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        prev_index = index
        index = solution.Value(routing.NextVar(index))
        total += routing.GetArcCostForVehicle(prev_index, index, 0)
    return order, total


def process_daily_unvisited(database, scope, all_fips, unvisited_by_fips,
                             fips_to_index, tsp_matrix, centroids_by_fips, time_limit_s):
    unvisited_fips = [f for f in all_fips if unvisited_by_fips.get(f, False)]
    cached = database.get_unvisited_route(scope)
    if cached is not None and sorted(cached['unvisited_fips']) == sorted(unvisited_fips):
        print(f'[{scope}] unvisited set unchanged ({len(unvisited_fips)} counties) -- skip')
        return

    print(f'[{scope}] unvisited set changed: {len(unvisited_fips)} counties -- recomputing')
    if len(unvisited_fips) <= 1:
        database.save_unvisited_route(scope, unvisited_fips, 0.0, unvisited_fips)
        print(f'[{scope}] saved trivial case: {len(unvisited_fips)} counties, 0.0 mi')
        return

    dist_matrix = build_distance_matrix(unvisited_fips, fips_to_index, tsp_matrix, centroids_by_fips)
    start = time.time()
    order, total_meters = solve_tour(dist_matrix, time_limit_s)
    elapsed = time.time() - start
    if order is None:
        print(f'[{scope}] WARNING: solver found no solution within {time_limit_s}s -- leaving cache as-is')
        return

    tour_fips = [unvisited_fips[i] for i in order]
    distance_miles = total_meters / _METERS_PER_MILE
    database.save_unvisited_route(scope, tour_fips, distance_miles, unvisited_fips)
    print(f'[{scope}] saved: {len(unvisited_fips)} counties, {distance_miles:,.1f} mi (solved in {elapsed:.1f}s)')


def process_full_tour(database, scope, all_fips, fips_to_index, tsp_matrix, centroids_by_fips, time_limit_s):
    cached = database.get_unvisited_route(scope)
    if cached is None:
        print(f'[{scope}] no cache row yet -- full-tour computation deferred to a later run')
        return
    if cached['full_tour_distance_miles'] is not None:
        return
    if len(all_fips) == 0:
        return

    print(f'[{scope}] computing one-time full-scope tour ({len(all_fips)} counties)...')
    if len(all_fips) == 1:
        database.save_full_tour(scope, all_fips, 0.0)
        print(f'[{scope}] full-tour saved trivial case: 0.0 mi')
        return

    dist_matrix = build_distance_matrix(all_fips, fips_to_index, tsp_matrix, centroids_by_fips)
    start = time.time()
    order, total_meters = solve_tour(dist_matrix, time_limit_s)
    elapsed = time.time() - start
    if order is None:
        print(f'[{scope}] WARNING: full-tour solver found no solution within {time_limit_s}s')
        return

    tour_fips = [all_fips[i] for i in order]
    distance_miles = total_meters / _METERS_PER_MILE
    database.save_full_tour(scope, tour_fips, distance_miles)
    print(f'[{scope}] full-tour saved: {distance_miles:,.1f} mi (solved in {elapsed:.1f}s)')


def main(scopes_filter=None):
    # scopes_filter: optional set of scope names (state abbrevs and/or
    # 'MAINLAND') to restrict this run to -- everything else is skipped
    # entirely, not even checked. Cron/the plain no-arg invocation always
    # processes every scope (scopes_filter=None); this exists so the
    # one-time backfill can be parallelized across several processes,
    # each handling a disjoint subset of scopes (see CLAUDE.md) -- safe
    # because each scope only ever writes its own row, and solve time is
    # ~fixed by the time-budget constants regardless of scope size, so a
    # simple static partition balances the parallel workers evenly.
    database = location_db.locationDB(db_name=config.database_location,
                                       fips_file=config.county_fips_file,
                                       country_file=config.country_file)

    print('Loading county centroids...')
    centroids_by_fips = load_county_centroids()

    print('Loading usa3100 distance matrix + locations...')
    tsp_matrix = load_tsp_matrix(config.usa3100_tsp_file)
    with open(config.usa3100_locations_file) as f:
        waterloo_locations = json.load(f)

    county_df = database.get_county_visits_dataframe()
    fips_to_index, unmatched = build_fips_to_matrix_index(county_df, waterloo_locations)
    non_ak_hi_unmatched = [u for u in unmatched if u[2] not in ('AK', 'HI')]
    print(f'FIPS->matrix-index map: {len(fips_to_index)} matched, {len(unmatched)} unmatched '
          f'({len(unmatched) - len(non_ak_hi_unmatched)} expected AK/HI, {len(non_ak_hi_unmatched)} unexpected)')
    for fips, name, state in non_ak_hi_unmatched:
        print(f'  WARNING: unmatched (falls back to haversine): {fips}  {name}, {state}')

    unvisited_by_fips = dict(zip(county_df['FIPS'], county_df['visited'] == False))

    scopes = {}
    for state in sorted(county_df['state'].unique()):
        scopes[state] = county_df[county_df['state'] == state]['FIPS'].tolist()
    mainland_mask = ~county_df['FIPS'].str[:2].isin(config.non_continental_fips_prefixes)
    scopes[MAINLAND_SCOPE] = county_df[mainland_mask]['FIPS'].tolist()

    if scopes_filter is not None:
        unknown = scopes_filter - scopes.keys()
        if unknown:
            print(f'WARNING: scopes_filter names unknown scopes, ignoring: {sorted(unknown)}')
        scopes = {k: v for k, v in scopes.items() if k in scopes_filter}
        print(f'Restricting this run to {len(scopes)} scope(s): {sorted(scopes.keys())}')

    for scope, all_fips in scopes.items():
        is_mainland = scope == MAINLAND_SCOPE
        daily_time_limit = DAILY_TIME_LIMIT_MAINLAND_S if is_mainland else DAILY_TIME_LIMIT_STATE_S
        full_tour_time_limit = FULL_TOUR_TIME_LIMIT_MAINLAND_S if is_mainland else FULL_TOUR_TIME_LIMIT_STATE_S
        process_daily_unvisited(database, scope, all_fips, unvisited_by_fips,
                                 fips_to_index, tsp_matrix, centroids_by_fips, daily_time_limit)
        process_full_tour(database, scope, all_fips,
                           fips_to_index, tsp_matrix, centroids_by_fips, full_tour_time_limit)

    print('Done.')


if __name__ == '__main__':
    # Optional: a comma-separated scope list (state abbrevs and/or
    # MAINLAND) as the sole CLI arg restricts this run to just those
    # scopes -- see main()'s scopes_filter docstring. No arg (the normal
    # cron/manual invocation) processes every scope, unchanged.
    _filter = set(sys.argv[1].split(',')) if len(sys.argv) > 1 else None
    main(_filter)
