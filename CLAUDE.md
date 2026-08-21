# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal location-tracking web app ("OwnTracks"-style). Phone GPS loggers (OwnTracks, ulogger, GPS Logger) POST position pings to a Flask server, which stores them in SQLite and renders Google Maps views of tracks, plus choropleth maps (via Plotly) of US counties/states/countries visited. Runs as a single Docker container behind a Cloudflare tunnel + Traefik, with Authelia handling auth on most routes.

## Running it

There is no local dev workflow beyond running the Flask app directly — this project is normally deployed via Docker Compose on the host machine, not run/tested by a coding agent.

- `docker-compose up --build` — builds from `config_files/Dockerfile` and starts the `location_track` service (container command: `sh /project/config_files/startup.sh`).
- `config_files/startup.sh` starts `cron` and launches gunicorn on `serve_flask_interface:app` (port 5000).
- Local/manual run (outside Docker): `python serve_flask_interface.py` runs Flask's dev server on port 8090.
- Requires a `.env` file (see `.env_template`) with `WEBAPP_DOMAIN`, `PASSWORD`, `GMAP_API_KEY`.
- No test suite or linter is configured. `test_flask.py` is a legacy/experimental copy of the Flask app, not a pytest suite.

### Data locations
- SQLite DB path is set in `config.py` (`database_location`, currently `/data/location.sqlite`). In the container, `/data` is bind-mounted from `/mnt/fast_storage/appdata/location_tracks`.
- The whole repo is bind-mounted into the container at `/project` (see `docker-compose.yml`), so code changes take effect without rebuilding the image — only a container restart is needed unless dependencies change.

## Architecture

### Database layer — `location_db.py`
`locationDB` wraps a SQLAlchemy Core (not ORM) SQLite database with four tables: `positions` (raw GPS points), `users` (maps a device/user string to an id), `counties` (all US counties, FIPS-keyed, with `visited`/`year`), `countries` (world countries, with `visited`). It self-migrates on construction (adds missing columns/tables via `ALTER TABLE`/`create_all`, checked on every startup) and seeds `counties`/`countries` from `config_files/state_and_county_fips_master.csv` and `config_files/countries.csv` if empty. Almost all cross-file interaction with data goes through this class — there is no ORM model layer elsewhere.

### Web layer — `serve_flask_interface.py`
The live entrypoint (`serve_flask_interface:app`, per `startup.sh`). Uses `flask_classful`'s `FlaskView` (class `FlaskApp`) to define routes as methods; `FlaskApp._initilization()` is called once at import time (a documented hack, see comment at bottom of file, to work around `flask_classful` re-running `__init__` per request). Key routes:
- `/` — main Google Map view of tracked points/polylines over a date range (`start`/`end` query params); `?points=1` switches from a polyline to individual deletable markers.
- `/log`, `/client/index.php` — ingestion endpoints for OwnTracks (`/log`) and ulogger (`/client/index.php`) apps.
- `/counties`, `/states`, `/countries`, `/state_view` — Plotly choropleth dashboards of visited areas, rendered into `templates/notdash.html`.
- `/log_flight` — scrapes a FlightAware KML URL and inserts it as a track (see also `addpoints_flightaware_kml.py`).
- `/execute_delete` — deletes a point by id (used by the marker delete-button popups on `/?points=1`).
- Most routes are gated by `@authelia_required`, which checks/verifies an `authelia_session` cookie against an external Authelia instance (`AUTHELIA_URL`); ingestion routes (`/log`, `/client/index.php`) are intentionally left open so logger apps can POST without a browser session.
- `plotly_flask.py` is an older/alternate version of this same app — not the one actually served; check `startup.sh`/`docker-compose.yml` before assuming which file is live.

### County/state "visited" computation — `add_county_visits.py`
Run periodically via cron (`config_files/cronjob_daily.sh` → `add_county_visits.py`), not on the request path. `CountyAdder` walks unprocessed `positions` rows in time order and does point-in-polygon lookups against the county GeoJSON (`config_files/gz_counties_*.json`, loaded via geopandas) to mark counties visited. Two optimizations that matter when touching this file:
1. `config.frequent_counties`/`frequent_areas` are bounding boxes for places visited often; points inside them are handled by cheap bbox checks (only the latest point per pass is polygon-tested) instead of a full GeoJSON lookup for every point.
2. `calculate_speeds` estimates speed from neighboring points and filters out points faster than `speed_thresh` (45 m/s) so that airplane flights don't falsely mark every county overflown as "visited."
Points are marked `county_processed` once handled so re-runs are incremental.

### Data ingestion scripts (one-off / cron, not imported by the web app)
Each of these populates `positions` via `location_db.insert_location`, from a different data source: `addpoints_google_takeout.py` (Google Takeout location history), `addpoints_gpx_google.py`/`add_gpx_route_certain_time.py` (GPX files), `addpoints_csv_flightradar.py`/`addpoints_flightaware_kml.py` (flight tracking exports), `add_historical_counties.py` (backfilling county visits for historical/manual data). `cleanup_remove_spurious_areas.py` and `tmp_show_one_state.py` are maintenance/debug utilities. `config_files/cronjob_15_min.sh` runs `addpoints_gpx_google.py` every 15 minutes.

### Travelling salesman experiments
`travelling_salesman.py` and `google_travelling_salesman.py` are standalone route-optimization experiments (using `python_tsp`, `fast_tsp`, `ortools`) against `config_files/usa3100_mixed.tsp` — unrelated to the location-logging/visited-counties functionality and not wired into the Flask app.

### Config — `config.py`
Central place for file paths (all under `config_files/`), the `frequent_counties`/`frequent_areas` bounding boxes used by `add_county_visits.py`, and the US state name ↔ abbreviation maps used throughout the templates and Flask routes. Import `config` rather than hardcoding these paths/maps elsewhere.

## Dev environment (this worktree)

This directory is a `git worktree` of `location_track` (prod), checked out on a separate branch, sharing the same `.git` history — commits made here are immediately visible from the prod checkout via `git log`, no push/pull needed. It runs as its own Docker container (`location_track_dev`, image `location_dev_img`) alongside prod, on its own DB copy (`/mnt/fast_storage/appdata/location_tracks_dev/location.sqlite`, cloned once from prod and now independent) and its own tunnel hostname (`dev_owntracks.exploretheworld.tech`). `config_files/startup.sh` here runs gunicorn with `--reload` and `serve_flask_interface.py` sets `TEMPLATES_AUTO_RELOAD = True` — both dev-only conveniences (not present in prod) so `.py` and template edits show up on refresh without a manual container restart. Prod (`location_track`, `main` branch, container `location_track`) intentionally lacks these.

## Known issues / open work

- **`notdash.html` choropleth still not truly full-bleed.** `#chart` is `position: fixed; width: 100vw; height: 100vh` behind a translucent-background `.page-foreground` overlay (title/buttons/table), with a `<meta name="viewport">` tag and `touch-action: none` + `scrollZoom: true` added so mobile pinch-zoom targets the map instead of the page — pinch-zoom now works, but the map still visually renders "in a box" rather than truly edge-to-edge. Not yet root-caused; likely something in how Plotly sizes/margins the geo subplot itself (`fig.update_geos`/`scope='usa'` projection padding) rather than the surrounding CSS, which is now believed correct.
- **States page (`/states`, `/state_view`) layout needs separate treatment** — it renders a stats table below the map (`_compute_table` output in `serve_flask_interface.py`) that the full-bleed background treatment doesn't suit as well as the map-only counties page; not yet addressed.
- **County-visit-years schema change not yet implemented** — `counties` table currently only stores a single `year` column, overwritten on each new visit, so "first time visited a county" and "years visited" can't be reconstructed. Planned fix: a child table `county_visits(fips, year)`, one row per visit-year, replacing the overwrite-on-update behavior in `location_db.set_visited_county`.
