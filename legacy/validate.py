#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Script to validate legacy results from past tournaments.  Note that this script will
replicate a bunch of code from both `run_auto.py` as well as `euchmgr.py`, for expediency.
LATER: we can reconcile/refactor for better reusability and integrity (or not).

CSV files
- 1 - Seed Draw
- 2 - Seed Bracket
- 3 - Seed Scores
- 4 - Seed Results
- 5 - Team Pairings
- 6 - Team Bracket
- 7 - Team Scores
- 8 - Team Results
"""

import csv
import sys
import os.path

from ckautils import parse_argv, typecast

from core import log
from database import db_init, db_close
from schema import rnd_pct, Bracket, TournStage, TournInfo, Player, SeedGame, Team, TournGame
import euchmgr
from euchmgr import (get_div_maps, fmt_team_name, fmt_player_list, compute_player_ranks,
                     compute_team_seeds)

FILE_DIR = os.path.dirname(os.path.realpath(__file__))
FLOAT_THRESH = 0.001

###################
# local functions #
###################

def upload_roster(csv_file: str) -> None:
    """Override for the corresponding `euchmgr` function.  Only expect `Num` and `Player`
    columns, as well as `Champ` (only required if reigning champ team was a three-headed
    monster)
    """
    COL_REQ = ['Num', 'Player']
    COL_MAP = {'Num'   : 'player_num',
               'Player': 'last_name',
               'Champ' : 'reigning_champ'}
    players = []
    nchamps = 0
    with open(os.path.join(FILE_DIR, csv_file), newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        for col in COL_REQ:
            assert col in header
        for i in range(len(header)):
            assert header[i] in COL_MAP
            header[i] = COL_MAP[header[i]]
        for row in reader:
            # NOTE: we will have a problem with string field values that are typecast to
            # non-strings (just to beware, don't really need to fix this)
            coerced = (typecast(x) for x in row)
            player_info = dict(zip(header, coerced))
            player = Player.create(**player_info)
            if player.reigning_champ:
                nchamps += 1
            players.append(player)

    # tweak, if `Champ` not specified (to keep the remaining code unchanged)
    if nchamps == 0:
        nchamps = 2

    # update tournament info (players, teams, etc.)
    nplayers = len(players)
    thm_teams = int(nchamps == 3)
    non_champs = nplayers - nchamps
    if non_champs & 0x01:
        thm_teams += 1
    nteams = non_champs // 2 + 1
    assert nteams == (nplayers - thm_teams) // 2

    tourn = TournInfo.get()
    tourn.players = nplayers
    tourn.teams = nteams
    tourn.thm_teams = thm_teams
    tourn.stage_compl = TournStage.PLAYER_ROSTER
    tourn.save()

def validate_player_nums() -> None:
    """Validate that low and contiguous player_nums have been assigned to all players.
    """
    if len(Player.nums_avail()) == 0:
        TournInfo.mark_stage_complete(TournStage.PLAYER_NUMS)
    # TODO: now assert lowness and contiguousness!!!

def build_seed_bracket(csv_file: str) -> list[SeedGame]:
    """Override for the corresponding `euchmgr` function.  The bracket matchups come from
    the specified CSV file (which we can cross-check for integrity with tournament info).
    """
    tourn = TournInfo.get()
    nplayers = tourn.players
    nrounds = tourn.seed_rounds

    COL_REF = ['Round', 'Table 1', 'Table 2', 'Table 3', 'Table 4',
               'Table 5', 'Table 6', 'Table 7', 'Table 8', 'Bye']
    games = []
    pl_map = Player.get_player_map()
    with open(os.path.join(FILE_DIR, csv_file), newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == COL_REF
        for rnd_i, row in enumerate(reader):
            rnd = int(row[0])
            assert rnd == rnd_i + 1
            seated = []
            for tbl_j, seats in enumerate(row[1:]):
                tbl = tbl_j + 1
                table = [int(x) for x in seats.split(',')]
                seated += table
                if len(table) < 4:
                    bye_players = fmt_player_list(pl_map, table)
                    table += [None] * (4 - len(table))
                    p1, p2, p3, p4 = table
                    tbl = None
                    label = f'{Bracket.SEED}-{rnd}-byes'
                    team1_name = team2_name = None
                else:
                    p1, p2, p3, p4 = table
                    label = f'{Bracket.SEED}-{rnd}-{tbl}'
                    team1_name = fmt_team_name(pl_map, [p1, p2])
                    team2_name = fmt_team_name(pl_map, [p3, p4])
                    bye_players = None
                info = {'round_num'  : rnd,
                        'table_num'  : tbl,
                        'label'      : label,
                        'player1_num': p1,
                        'player2_num': p2,
                        'player3_num': p3,
                        'player4_num': p4,
                        'team1_name' : team1_name,
                        'team2_name' : team2_name,
                        'bye_players': bye_players}
                game = SeedGame.create(**info)
                games.append(game)
                if game.bye_players:
                    game.insert_player_games()

            assert len(seated) == nplayers
            assert set(seated) == set(range(1, nplayers + 1))
        assert rnd == nrounds

    tourn.complete_stage(TournStage.SEED_BRACKET)
    return games

def load_seed_games(csv_file: str) -> None:
    """Override for the corresponding `euchmgr` function.
    """
    tourn = TournInfo.get()
    nplayers = tourn.players
    nrounds = tourn.seed_rounds

    COL_REF = ['Num', 'Player', 'Wins', 'Losses', 'Win Pct',
               'PF1', 'PF2', 'PF3', 'PF4', 'PF5', 'PF6', 'PF7', 'PF8', 'PF Total',
               'PA1', 'PA2', 'PA3', 'PA4', 'PA5', 'PA6', 'PA7', 'PA8', 'PA Total', 'Pts Pct']
    scores = {}
    with open(os.path.join(FILE_DIR, csv_file), newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == COL_REF
        for row in reader:
            pl_num   = typecast(row[0])
            pl_name  = row[1]
            wins     = typecast(row[2])
            losses   = typecast(row[3])
            win_pct  = typecast(row[4])
            ptf_list = [typecast(x) for x in row[5:13]]
            ptf_tot  = typecast(row[13])
            pta_list = [typecast(x) for x in row[14:22]]
            pta_tot  = typecast(row[22])
            pts_pct  = typecast(row[23])
            assert len(ptf_list) == nrounds
            assert len(pta_list) == nrounds
            scores[pl_num] = list(zip(ptf_list, pta_list))
        assert len(scores) == nplayers

    sort_key = lambda x: (x.round_num, x.table_num)
    for game in sorted(SeedGame.iter_games(), key=sort_key):
        rnd_i = game.round_num - 1
        p1_scores = scores[game.player1_num][rnd_i]
        p2_scores = scores[game.player2_num][rnd_i]
        p3_scores = scores[game.player3_num][rnd_i]
        p4_scores = scores[game.player4_num][rnd_i]
        assert p1_scores == p2_scores
        assert p3_scores == p4_scores
        assert p3_scores == tuple(reversed(p1_scores))
        game.add_scores(*p1_scores)
        game.save()

        if game.winner:
            game.update_player_stats()
            game.insert_player_games()

    compute_player_ranks()
    TournInfo.mark_stage_complete(TournStage.SEED_RESULTS)

def validate_seed_results(csv_file: str) -> None:
    """Check computed results against spreadsheet results.  Flag any field discrepancies
    by player.
    """
    pl_map = {}  # by name
    for pl in Player.iter_players():
        pl_map[pl.name] = pl

    COL_MAP = {'Rank'   : 'player_rank',
               'Player' : 'name',
               'Win Pct': 'seed_win_pct',
               'Pts Pct': 'seed_pts_pct'}
    FIX_COL = ['player_rank']
    with open(os.path.join(FILE_DIR, csv_file), newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == list(COL_MAP.keys())
        for row in reader:
            coerced = (typecast(x) for x in row)
            pl_res = dict(zip(COL_MAP.values(), coerced))
            pl = pl_map[pl_res['name']]
            for col in pl_res:
                if isinstance(pl_res[col], float):
                    if abs(pl_res[col] - getattr(pl, col)) < FLOAT_THRESH:
                        continue
                elif pl_res[col] == getattr(pl, col):
                    continue

                if col in FIX_COL:
                    log.notice(f"Overwriting mismatch for {pl.name}: "
                               f"{col} = {pl_res[col]} ({getattr(pl, col)})")
                    # FIX: for now, we are always just doing the adjustment in-place; for
                    # rankings, we will want to do this in the associated "_adj" column
                    # instead!!!
                    setattr(pl, col, pl_res[col])
                    pl.save()
                else:
                    log.notice(f"Mismatch for {pl.name}: "
                               f"{col} = {pl_res[col]} ({getattr(pl, col)})")

def load_partner_picks(csv_file: str) -> None:
    """Assumes champ team is pre-picked (in that we don't do the picking and/or checking
    for keeping the champ team together)
    """
    tourn = TournInfo.get()
    nplayers = tourn.players
    nteams = tourn.teams

    pl_map = {}  # by name
    for pl in Player.iter_players():
        pl_map[pl.name] = pl
    assert len(pl_map) == nplayers

    COL_REF = ['Team Num', 'Player 1', 'Rank 1', 'Player 2', 'Rank 2', 'Comb Rank',
               'Team Seed', 'Div Seed', 'Div', 'Team ID', 'Team Name']
    picks = []
    with open(os.path.join(FILE_DIR, csv_file), newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == COL_REF
        for row in reader:
            coerced = (typecast(x) for x in row)
            pick = dict(zip(COL_REF, coerced))
            player_name = pick['Player 1']
            partner_names = pick['Player 2'].split(' / ', 1)
            assert len(partner_names) in (1, 2)

            player = pl_map[player_name]
            partners = [pl_map[x] for x in partner_names]
            player.set_partners(*partners)
            player.save(cascade=True)
            picks.append(player)

        assert len(picks) == nteams

    TournInfo.mark_stage_complete(TournStage.PARTNER_PICK)

def load_team_seeds(csv_file: str) -> None:
    """
    """
    tourn = TournInfo.get()
    nteams = tourn.teams
    ndivs = tourn.divisions
    assert ndivs == 2  # logic for this is hard-wired below

    tm_map = {}  # by name
    for tm in compute_team_seeds(no_save=True):
        tm_map[tm.team_name] = tm
    assert len(tm_map) == nteams

    COL_MAP = {'Team Num'  : 'team_ord',
               'Player 1'  : 'picker',
               'Rank 1'    : 'picker_rank',
               'Player 2'  : 'partner',
               'Rank 2'    : 'partner_rank',
               'Comb Rank' : 'comb_rank',
               'Team Seed' : 'team_seed',
               'Div Seed'  : 'div_seed',
               'Div'       : 'div_name',
               'Team ID'   : 'brckt_seed',
               'Team Name' : 'team_name'}
    DIV_MAP = {'A': 1, 'B': 2}
    FIX_COL = ['team_seed', 'div_num', 'div_seed']
    teams = []
    with open(os.path.join(FILE_DIR, csv_file), newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == list(COL_MAP.keys())
        for row in reader:
            coerced = (typecast(x) for x in row)
            tm_res = dict(zip(COL_MAP.values(), coerced))
            tm_res['div_num'] = DIV_MAP[tm_res['div_name']]
            tm = tm_map[tm_res['team_name']]

            for col in FIX_COL:
                if tm_res[col] == getattr(tm, col):
                    continue

                log.notice(f"Overwriting mismatch for {tm.team_name}: "
                           f"{col} = {tm_res[col]} ({getattr(tm, col)})")
                # FIX: for now, we are always just doing the adjustment in-place; for
                # rankings, we will want to do this in the associated "_adj" column
                # instead!!!
                setattr(tm, col, tm_res[col])

            tm.save()
            teams.append(tm)

        assert len(teams) == nteams

    tourn.complete_stage(TournStage.TEAM_SEEDS)

def load_tourn_bracket(csv_file: str) -> list[TournGame]:
    """
    """
    tourn = TournInfo.get()
    ndivs = tourn.divisions
    nrounds = tourn.tourn_rounds

    # don't make assumptions on how divisions are assigned, just go off the actual count
    # of teams in each division--NOTE that div_maps is keyed off of the actual division
    # number (1-based), whereas the div_i index for the loop below is 0-based (for
    # consistency with the other indexes), this is a little messy, sorry!
    div_maps = get_div_maps(tourn)

    games = []
    for div_i in range(ndivs):
        assert div_i + 1 in div_maps
        div_map = div_maps[div_i + 1]
        brckt_teams = len(div_map)
        bye_div_seed = brckt_teams + 1  # TODO: only if odd number of teams!!!
        bracket_file = f'rr-{brckt_teams}-{nrounds}.csv'  # need to reconcile with Bracket.TOURN!!!
        with open(BracketsFile(bracket_file), newline='') as f:
            reader = csv.reader(f)
            for rnd_j, row in enumerate(reader):
                seats = (int(x) for x in row)
                tbl_k = 0
                while table := list(islice(seats, 0, 2)):
                    if bye_div_seed in table:
                        t1, t2 = sorted(table)
                        assert t2 == bye_div_seed
                        label = f'{Bracket.TOURN}-{div_i+1}-{rnd_j+1}-bye'
                        team1 = div_map[t1]
                        info = {'div_num'       : div_i + 1,
                                'round_num'     : rnd_j + 1,
                                'table_num'     : None,
                                'label'         : label,
                                'team1'         : team1,
                                'team2'         : None,
                                'team1_name'    : None,
                                'team2_name'    : None,
                                'bye_team'      : team1.team_name,
                                'team1_div_seed': team1.div_seed,
                                'team2_div_seed': None}
                    else:
                        t1, t2 = table
                        label = f'{Bracket.TOURN}-{div_i+1}-{rnd_j+1}-{tbl_k+1}'
                        team1 = div_map[t1]
                        team2 = div_map[t2]
                        info = {'div_num'       : div_i + 1,
                                'round_num'     : rnd_j + 1,
                                'table_num'     : tbl_k + 1,
                                'label'         : label,
                                'team1'         : team1,
                                'team2'         : team2,
                                'team1_name'    : team1.team_name,
                                'team2_name'    : team2.team_name,
                                'bye_team'      : None,
                                'team1_div_seed': team1.div_seed,
                                'team2_div_seed': team2.div_seed}
                        tbl_k += 1
                    game = TournGame.create(**info)
                    games.append(game)
                    if game.bye_team:
                        game.insert_team_games()

    tourn.complete_stage(TournStage.TOURN_BRACKET)
    return games

########
# main #
########

# the following functions must exist in either the current module or in `euchmgr` (checked
# in that order)--NOTE, for now, we only go as far as building the playoff bracket; LATER,
# we can load and validation playoff results and final tournament rankings as well!!!
ALL_FUNCS = [
    'tourn_create',
    'upload_roster',
    'validate_player_nums',
    'build_seed_bracket',
    'load_seed_games',
    'validate_seed_round',
    'compute_player_ranks',
    'validate_seed_results',
    'prepick_champ_partners',
    'load_partner_picks',
    'build_tourn_teams',
    'load_team_seeds',
    'load_tourn_bracket',
    'load_tourn_games',
    'validate_tourn',
    'compute_team_ranks',
    'build_playoff_bracket'
]

def get_func_args(func: str, tourn_name: str) -> dict:
    """Return dict representing arguments to pass into ``func``
    """
    func_args = {
        'tourn_create'         : {'force': True},
        'upload_roster'        : {'csv_file': f"{tourn_name}_results-1.csv"},
        'build_seed_bracket'   : {'csv_file': f"{tourn_name}_results-2.csv"},
        'load_seed_games'      : {'csv_file': f"{tourn_name}_results-3.csv"},
        'validate_seed_round'  : {'finalize': True},
        'compute_player_ranks' : {'finalize': True},
        'validate_seed_results': {'csv_file': f"{tourn_name}_results-4.csv"},
        'load_partner_picks'   : {'csv_file': f"{tourn_name}_results-5.csv"},
        'load_team_seeds'      : {'csv_file': f"{tourn_name}_results-5.csv"},
        'load_tourn_bracket'   : {'csv_file': f"{tourn_name}_results-6.csv"},
        'load_tourn_games'     : {'csv_file': f"{tourn_name}_results-7.csv"},
        'validate_tourn'       : {'finalize': True},
        'compute_team_ranks'   : {'finalize': True},
        'build_playoff_bracket': {'bracket': Bracket.SEMIS}
    }

    if func not in func_args:
        return {}
    return func_args[func]

def main() -> int:
    """Validate framework against legacy tournament results

    Usage: python -m legacy.validate <tourn_name> <func_list> [<addl_args>]

    where ``func_list`` is a comma-separated list of functions to run, or ``'all'``

    Functions:
      - tourn_create
      - upload_roster
      - validate_player_nums
      - build_seed_bracket
      - load_seed_games
      - tabulate_seed_round
      - compute_player_ranks
      - prepick_champ_partners
      - load_partner_picks
      - build_tourn_teams
      - load_team_seeds
      - load_tourn_bracket
      - load_tourn_games
      - tabulate_tourn
      - compute_team_ranks
      - build_playoff_bracket

    Note that data files with name ``<tourn_name>_results-<N>.csv`` (where N = 1-8) will
    be assumed, and ``addl_args`` represents keyword args that will be passed into the
    specified function (must be a single function, in this case).
    """
    usage = lambda x: x + "\n\n" + main.__doc__
    if len(sys.argv) < 2:
        return usage("Tournament name not specified")
    if len(sys.argv) < 3:
        return usage("Validation function(s) not specified")

    tourn_name = sys.argv[1]
    func_list = sys.argv[2]
    if func_list == 'all':
        funcs = ALL_FUNCS
    else:
        funcs = func_list.split(',')
        for func in funcs:
            if func not in ALL_FUNCS:
                return usage(f"Unknown function '{func}'")

    args, kwargs = parse_argv(sys.argv[3:])  # pick up additional args
    if args:
        return usage("Unknown args: " + ' '.join(args))
    if kwargs and len(funcs) > 1:
        return usage("Extra args only supported if a single function is specified")
    db_init(tourn_name, force=True)
    for func in funcs:
        if func in globals():
            func_call = globals()[func]
        else:
            func_call = getattr(euchmgr, func)
        func_args = get_func_args(func, tourn_name)
        func_call(**(func_args | kwargs))  # will throw exceptions on error
    db_close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
