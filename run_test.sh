#!/usr/bin/env bash

TOURN="${TOURN:-nola_2025}"
ROSTER="${ROSTER:-nola_2025_roster.csv}"

python -m euchmgr "${TOURN}" tourn_create force=t
echo "Tournament \"${TOURN}\" created"
echo -n "Uploading roster..."
echo "done"
python -m euchmgr "${TOURN}" upload_roster "${ROSTER}"
echo -n "Generating player nums..."
echo "done"
python -m euchmgr "${TOURN}" generate_player_nums
echo -n "Building seeding bracket..."
echo "done"
python -m euchmgr "${TOURN}" build_seed_bracket
echo -n "Creating fake seeding results..."
echo "done"
python -m euchmgr "${TOURN}" fake_seed_games
echo -n "Validating seeding results..."
echo "done"
python -m euchmgr "${TOURN}" validate_seed_round
echo -n "Computing player rankings..."
echo "done"
python -m euchmgr "${TOURN}" compute_player_seeds
echo -n "Prepicking champ partners..."
echo "done"
python -m euchmgr "${TOURN}" prepick_champ_partners
echo -n "Creating fake partner picks..."
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
echo -n "Creating fake tournament results..."
echo "done"
python -m euchmgr "${TOURN}" fake_tourn_games
echo -n "Validating tournament results..."
echo "done"
python -m euchmgr "${TOURN}" validate_tourn
echo -n "Computing tournament rankings..."
echo "done"
python -m euchmgr "${TOURN}" compute_team_ranks
