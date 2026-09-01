#! /bin/sh

# -n (non-blocking): if a previous day's run is somehow still going (the
# one-time full-scope backfill can take a long time the first several
# days -- see CLAUDE.md), this exits immediately without running anything.
# Own lock file, separate from county_processing.lock -- this only reads
# counties.visited and writes the unrelated unvisited_routes table, no
# real contention with the ingestion pipeline.
flock -n /tmp/tsp_route_processing.lock -c "/usr/local/bin/python /project/compute_unvisited_routes.py"
