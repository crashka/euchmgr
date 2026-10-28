#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os.path
from datetime import datetime
from statistics import mean, median, stdev
from glob import glob

USAGE = "python -m req_time_anly [<log file>]"

if len(sys.argv) > 2:
    sys.exit(USAGE)

if len(sys.argv) == 2:
    input_stream = open(sys.argv[1], 'r')
else:
    assert not sys.stdin.isatty()
    input_stream = sys.stdin

REQ_TIMES: dict[str, list[float]] = {}
TS_TIMES:  dict[int, list[float]] = {}

for i, line in enumerate(input_stream):
    stridx = line.find('req time:')
    if stridx < 0:
        continue

    # get request information
    _, _, method, path, ms, chk = line[stridx:].split(' ', 5)
    assert chk.rstrip() == 'ms'
    path_parts = path.rstrip(':').split('/', 4)
    assert path_parts[0] == ''
    if len(path_parts) == 4:
        if path_parts[3] != '':
            subparts = path_parts[3].split('-')
            if subparts[0] in ('sd', 'rr', 'sf', 'fn'):
                path_parts[3] = "<game_label>"
            path = '/'.join(path_parts)
    req = f"{method} {path.rstrip(':')}"

    # get timestamp information (to one second granularity)
    dt = datetime.fromisoformat(line[:19])
    ts = int(dt.timestamp())

    #print(f"{i:5d}: {req} - {ms} ms")
    if req not in REQ_TIMES:
        REQ_TIMES[req] = []
    REQ_TIMES[req].append(float(ms))

    if ts not in TS_TIMES:
        TS_TIMES[ts] = []
    TS_TIMES[ts].append(float(ms))

input_stream.close

# backfill missing timestamps
min_ts = min(TS_TIMES.keys())
max_ts = max(TS_TIMES.keys())
print(f"Elapsed time: {max_ts - min_ts} secs")
missing_ts = set(range(min_ts, max_ts + 1)) - set(TS_TIMES.keys())
#print(f"Backfilling missing timestamps: {len(missing_ts)}")
TS_TIMES.update({ts: [] for ts in missing_ts})
assert len(TS_TIMES) == max_ts - min_ts + 1

# stats by request target
REQ_STATS: dict[str, tuple[int, float, ...]] = {}

for req, times in REQ_TIMES.items():
    REQ_STATS[req] = (len(times), sum(times), max(times), mean(times), median(times),
                      stdev(times) if len(times) > 1 else 0.0)

# stats by timestamp
TS_STATS: dict[int, tuple[int, float, ...]] = {}

for ts, times in TS_TIMES.items():
    if len(times) == 0:
        TS_STATS[ts] = (len(times), None, None, None, None, None)
    else:
        TS_STATS[ts] = (len(times), sum(times), max(times), mean(times), median(times),
                        stdev(times) if len(times) > 1 else 0.0)

RPT_BASE  = "req_time_rpt"
HIST_BASE = "req_time_hist"

if os.path.exists(f"{RPT_BASE}.csv") or os.path.exists(f"{HIST_BASE}.csv"):
    rpt_files = glob(f'{RPT_BASE}*.csv')
    hist_files = glob(f'{HIST_BASE}*.csv')
    max_num = 0
    for file in rpt_files + hist_files:
        parts = file.removesuffix('.csv').split('_')
        if len(parts) != 4:
            continue
        if not parts[-1].isdigit():
            continue
        max_num = max(max_num, int(parts[-1]))
    rpt_file = f"{RPT_BASE}_{max_num+1}.csv"
    hist_file = f"{HIST_BASE}_{max_num+1}.csv"
else:
    rpt_file = f"{RPT_BASE}.csv"
    hist_file = f"{HIST_BASE}.csv"

# output CSV data by request target
print(f"Wriing data by request URL to {rpt_file}")
with open(rpt_file, 'w') as f:
    print("Request,Count,\"Agg Time\",Max,Mean,Median,Stdev", file=f)
    for req, stats in REQ_STATS.items():
        float_stats = [str(round(x, 1)) for x in stats[1:]]  # as strings (for joinability)
        print(f"\"{req}\",{stats[0]},{','.join(float_stats)}", file=f)

# output CSV data by timestamp
print(f"Wriing data as timestamp histogram to {hist_file}")
with open(hist_file, 'w') as f:
    print("Timestamp,Count,\"Agg Time\",Max,Mean,Median,Stdev", file=f)
    for ts in sorted(TS_STATS.keys()):
        dt_iso = datetime.fromtimestamp(ts).isoformat(sep=' ')
        stats = TS_STATS[ts]
        assert len(stats) == 6
        if stats[0] == 0:
            print(f"\"{dt_iso}\",{stats[0]},,,,", file=f)
        else:
            float_stats = [str(round(x, 1)) for x in stats[1:]]  # as strings (for joinability)
            print(f"\"{dt_iso}\",{stats[0]},{','.join(float_stats)}", file=f)

# report by request target
print("\nOverview of Data by Aggregate Time (seconds, descending)\n")
print(f"{'Request':40}\t{'Count':>6}\t{'Agg Tim'}\t{'Max':>6}\t{'Mean':>6}\t"
      f"{'Median':>6}\t{'Stdev':>6}")
print(f"{'-' * 40}\t{'-' * 6}\t{'-' * 7}\t{'-' * 6}\t{'-' * 6}\t{'-' * 6}\t{'-' * 6}")
for req in sorted(REQ_STATS.keys(), key=lambda x: -REQ_STATS[x][1]):
    stats = REQ_STATS[req]
    print(f"{req:40}\t{stats[0]:6d}\t{stats[1]:7.1f}\t{stats[2]:6.1f}\t"
          f"{stats[3]:6.1f}\t{stats[4]:6.1f}\t{stats[5]:6.1f}")

sys.exit(0)
