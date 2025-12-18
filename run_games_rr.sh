#!/usr/bin/env bash

set -e

TOURN="${TOURN:-nola_2025}"
ROSTER="${ROSTER:-nola_2025_roster.csv}"

nteams=20
nrounds=8

LIMIT=${1:-10}
LOOPS=${2:-$(((nteams / 2 * nrounds - 1) / LIMIT + 1))}

echo "LIMIT = " ${LIMIT}
echo "LOOPS = " ${LOOPS}

for i in $(seq 1 ${LOOPS}) ; do
    read -p "Press any key to create ${LIMIT} fake tournament results..." -n1 -s
    echo "done"
    python -m euchmgr "${TOURN}" fake_tourn_games limit=${LIMIT}
done

echo -n "Validating tournament results..."
echo "done"
python -m euchmgr "${TOURN}" validate_tourn finalize=t
echo -n "Computing tournament rankings..."
echo "done"
python -m euchmgr "${TOURN}" compute_team_ranks finalize=t
