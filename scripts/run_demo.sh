#!/usr/bin/env bash

scriptdir="$(dirname $(readlink -f $0))"
cd ${scriptdir}/..
PATH="venv/bin:${PATH}"

set -e

TOURN="${TOURN:-nola_2025}"
ROSTER="${ROSTER:-nola_2025_roster.csv}"

echo -n "Creating tournament \"${TOURN}\"..."
echo "done"
python -m euchmgr "${TOURN}" tourn_create force=t
read -p "Press any key to upload roster..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" upload_roster "${ROSTER}"
echo -n "Generating player nums..."
echo "done"
python -m euchmgr "${TOURN}" generate_player_nums
echo -n "Building seeding bracket..."
echo "done"
python -m euchmgr "${TOURN}" build_seed_bracket
read -p "Press any key to create fake seeding results..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" fake_seed_games
echo -n "Validating seeding results..."
echo "done"
python -m euchmgr "${TOURN}" validate_seed_round finalize=t
echo -n "Computing player rankings..."
echo "done"
python -m euchmgr "${TOURN}" compute_player_ranks finalize=t
echo -n "Prepicking champ partners..."
echo "done"
python -m euchmgr "${TOURN}" prepick_champ_partners
read -p "Press any key to create fake partner picks..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" fake_pick_partners
echo -n "Building tournament teams..."
echo "done"
python -m euchmgr "${TOURN}" build_tourn_teams
echo -n "Computing tournament team seeds..."
echo "done"
python -m euchmgr "${TOURN}" compute_team_seeds
echo -n "Building tournament brackets..."
echo "done"
python -m euchmgr "${TOURN}" build_tourn_bracket
read -p "Press any key to create fake tournament results..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" fake_tourn_games
echo -n "Validating tournament results..."
echo "done"
python -m euchmgr "${TOURN}" validate_tourn finalize=t
echo -n "Computing tournament rankings..."
echo "done"
python -m euchmgr "${TOURN}" compute_team_ranks finalize=t
