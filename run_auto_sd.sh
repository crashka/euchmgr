#!/usr/bin/env bash

set -e

TOURN="${TOURN:-nola_2025}"
ROSTER="${ROSTER:-nola_2025_roster.csv}"

nplayers=42
nrounds=8

LIMIT=${1:-10}
LOOPS=${2:-$(((nplayers / 4 * nrounds - 1) / LIMIT + 1))}
SLEEP=${3:-5}

echo "LIMIT = " ${LIMIT}
echo "LOOPS = " ${LOOPS}
echo "SLEEP = " ${SLEEP}

echo -n "Creating tournament \"${TOURN}\"..."
echo "done"
python -m euchmgr "${TOURN}" tourn_create force=t
echo -n "Uploading roster..."
echo "done"
python -m euchmgr "${TOURN}" upload_roster "${ROSTER}"
echo -n "Generating player nums..."
echo "done"
python -m euchmgr "${TOURN}" generate_player_nums
echo -n "Building seeding bracket..."
echo "done"
python -m euchmgr "${TOURN}" build_seed_bracket

for i in $(seq 1 ${LOOPS}) ; do
    echo -n "Creating ${LIMIT} fake seeding results..."
    echo "done"
    python -m euchmgr "${TOURN}" fake_seed_games limit=${LIMIT}
    sleep $SLEEP
done

echo -n "Validating seeding results..."
echo "done"
python -m euchmgr "${TOURN}" validate_seed_round finalize=t
echo -n "Computing player rankings..."
echo "done"
python -m euchmgr "${TOURN}" compute_player_ranks finalize=t
echo -n "Prepicking champ partners..."
echo "done"
python -m euchmgr "${TOURN}" prepick_champ_partners
