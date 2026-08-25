#! /usr/bin/env python

# One-off historical replay: sweeps every position (including ones the
# ongoing cron pipeline already finished with) to backfill county_visits
# with every distinct visit-year per county, not just the most recent one.
# Safe to run against a live site and safe to re-run -- see CLAUDE.md's
# "county visit-years" notes for the full design rationale. Invoke this
# directly (docker exec, wrapped in flock -- see cronjob_daily.sh and
# CLAUDE.md), never via cron.

from add_county_visits import CountyAdder

if __name__ == "__main__":
    adder = CountyAdder(mode='backfill')
    adder.iterate_until_done()
