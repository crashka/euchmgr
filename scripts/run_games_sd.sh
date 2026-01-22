#!/usr/bin/env bash

scriptdir="$(dirname $(readlink -f $0))"
cd ${scriptdir}/..
PATH="venv/bin:${PATH}"

set -e

TOURN="${TOURN:-nola_2025}"
ROSTER="${ROSTER:-nola_2025_roster.csv}"

nplayers=42
nrounds=8

LIMIT=${1:-10}
LOOPS=${2:-$(((nplayers / 4 * nrounds - 1) / LIMIT + 1))}

echo "LIMIT = " ${LIMIT}
echo "LOOPS = " ${LOOPS}

for i in $(seq 1 ${LOOPS}) ; do
    read -p "Press any key to create ${LIMIT} fake seeding results..." -n1 -s
    echo "done"
    python -m euchmgr "${TOURN}" fake_seed_games limit=${LIMIT}
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
