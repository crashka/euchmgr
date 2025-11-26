#!/usr/bin/env bash

TOURN="${TOURN:-nola_2025}"
ROSTER="${ROSTER:-nola_2025_roster.csv}"

python -m euchmgr "${TOURN}" tourn_create force=t
echo "Tournament \"${TOURN}\" created"
read -p "Press any key to upload roster..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" upload_roster "${ROSTER}"
read -p "Press any key to generate player nums..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" generate_player_nums
read -p "Press any key to build seeding bracket..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" build_seed_bracket
read -p "Press any key to create fake seeding results..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" fake_seed_games
read -p "Press any key to validate seeding results..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" validate_seed_round
read -p "Press any key to compute player rankings..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" compute_player_seeds
read -p "Press any key to prepick champ partners..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" prepick_champ_partners
read -p "Press any key to create fake partner picks..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" fake_pick_partners
read -p "Press any key to build tournament teams..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" build_tourn_teams
read -p "Press any key to compute tournament team seeds..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" compute_team_seeds
read -p "Press any key to build tournament brackets..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" build_tourn_bracket
read -p "Press any key to create fake tournament results..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" fake_tourn_games
read -p "Press any key to validate tournament results..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" validate_tourn
read -p "Press any key to compute tournament rankings..." -n1 -s
echo "done"
python -m euchmgr "${TOURN}" compute_team_ranks
