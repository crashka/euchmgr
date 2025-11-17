#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
To do list:
- compute intermediary results/stats when scores are entered
  - related: create teams as picks are made?
- use head-to-head record for tie-breakers
- implement playoff rounds

Fix in bracket generation (`round-robin` project):
- highest seeds (across divisions) should get byes (if any)
- bracketology fairness for inter-divisional play
"""

import random
from itertools import islice
import csv
import os

from core import DataFile
from database import db_init, db_name
from schema import schema_create, TournStage, TournInfo, Player, SeedGame, Team, TournGame

BYE_TEAM = '-- (bye) --'

#####################
# utility functions #
#####################

def fmt_player_list(player_nums: list[int]) -> str:
    """
    """
    pl_map = Player.get_player_map()
    nick_names = [pl_map[p].nick_name for p in player_nums]
    return ' / '.join(nick_names)

def fmt_team_name(player_nums: list[int]) -> str:
    """
    """
    pl_map = Player.get_player_map()
    nick_names = [pl_map[p].nick_name for p in player_nums]
    return ' / '.join(nick_names)

#####################
# euchmgr functions #
#####################

def tourn_create(timeframe: str = None, venue: str = None, **kwargs) -> TournInfo:
    """Create a tournament with specified name (must be unique).

    Additional `kwargs` are passed on to `schema_create`
    """
    schema_create(**kwargs)

    info = {'name'       : db_name(),  # db_name is same as tournament name
            'timeframe'  : timeframe,
            'venue'      : venue,
            'stage_compl': TournStage.TOURN_CREATE}
    tourn = TournInfo.create(**info)
    return tourn

def upload_roster(csv_path: str) -> None:
    """Create all Player records based on specified roster file (CSV).  The header row
    must specify the required info field names for the model object.
    """
    players = []
    nchamps = 0
    with open(csv_path, newline='') as f:
        reader = csv.reader(f)
        header = next(reader)  # TODO: check for required fields!!!
        for row in reader:
            player_info = dict(zip(header, row))
            # note that type coercion is expected to just work here (all CSV values come
            # in as text strings)
            player = Player.create(**player_info)
            if player.reigning_champ:
                nchamps += 1
            players.append(player)

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

def generate_player_nums(rand_seed: int = None) -> None:
    """Generate random values for player_num, akin to picking numbered ping pong balls out
     of a bag.

    Note: player_nums can also be specified in the roster file or manually assigned, which
    in either case this function should not be called (would overwrite existing values).
    """
    my_rand = random.Random
    if isinstance(rand_seed, int):
        my_rand.seed(rand_seed)  # for reproducible debugging only

    pl_list = list(Player.iter_players())
    nplayers = len(pl_list)
    ords = iter(random.sample(range(nplayers), nplayers))
    for player in pl_list:
        player.player_num = next(ords) + 1
        player.save()

    TournInfo.mark_stage_complete(TournStage.PLAYER_NUMS)

def build_seed_bracket() -> list[SeedGame]:
    """Populate seed round matchups and byes (in `seed_round` table) based on tournament
    parameters and uploaded roster.

    """
    tourn = TournInfo.get()
    nplayers = tourn.players
    nrounds = tourn.seed_rounds
    bracket_file = f'seed-{nplayers}-{nrounds}.csv'

    games = []
    with open(DataFile(bracket_file), newline='') as f:
        reader = csv.reader(f)
        for rnd_i, row in enumerate(reader):
            seats = (int(x) for x in row)
            tbl_j = 0
            while table := list(islice(seats, 0, 4)):
                if len(table) < 4:
                    bye_players = fmt_player_list(table)
                    table += [None] * (4 - len(table))
                    p1, p2, p3, p4 = table
                    table_num = None
                    label = f'seed-r{rnd_i+1}-byes'
                    team1_name = team2_name = None
                else:
                    p1, p2, p3, p4 = table
                    table_num = tbl_j + 1
                    label = f'seed-r{rnd_i+1}-t{tbl_j+1}'
                    team1_name = fmt_team_name([p1, p2])
                    team2_name = fmt_team_name([p3, p4])
                    bye_players = None
                info = {'round_num'  : rnd_i + 1,
                        'table_num'  : table_num,
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
                tbl_j += 1

    tourn.complete_stage(TournStage.SEED_BRACKET)
    return games

def fake_seed_games() -> None:
    """Generates random team points and determines winner for each seed game
    """
    for game in SeedGame.iter_games():
        winner_pts = 10
        loser_pts = random.randrange(10)
        if random.randrange(2) > 0:
            game.add_scores(winner_pts, loser_pts)
        else:
            game.add_scores(loser_pts, winner_pts)
        game.save()

    TournInfo.mark_stage_complete(TournStage.SEED_RESULTS)

def tabulate_seed_round() -> None:
    """
    """
    pl_map = Player.get_player_map()

    for player in pl_map.values():
        assert player.seed_wins is None
        assert player.seed_losses is None
        assert player.seed_pts_for is None
        assert player.seed_pts_against is None
        player.seed_wins = 0
        player.seed_losses = 0
        player.seed_pts_for = 0
        player.seed_pts_against = 0

    for game in SeedGame.iter_games():
        player1 = pl_map[game.player1_num]
        player2 = pl_map[game.player2_num]
        player3 = pl_map[game.player3_num]
        player4 = pl_map[game.player4_num]

        if game.winner == game.team1_name:
            player1.seed_wins += 1
            player2.seed_wins += 1
            player3.seed_losses += 1
            player4.seed_losses += 1
        else:
            player1.seed_losses += 1
            player2.seed_losses += 1
            player3.seed_wins += 1
            player4.seed_wins += 1

        player1.seed_pts_for += game.team1_pts
        player2.seed_pts_for += game.team1_pts
        player3.seed_pts_for += game.team2_pts
        player4.seed_pts_for += game.team2_pts
        player1.seed_pts_against += game.team2_pts
        player2.seed_pts_against += game.team2_pts
        player3.seed_pts_against += game.team1_pts
        player4.seed_pts_against += game.team1_pts

    for player in pl_map.values():
        ngames = player.seed_wins + player.seed_losses
        totpts = player.seed_pts_for + player.seed_pts_against
        player.seed_win_pct = player.seed_wins / ngames * 100.0
        player.seed_pts_diff = player.seed_pts_for - player.seed_pts_against
        player.seed_pts_pct = player.seed_pts_for / totpts * 100.0
        player.save()

    TournInfo.mark_stage_complete(TournStage.SEED_TABULATE)

def compute_player_seeds() -> None:
    """
    """
    pl_list = Player.get_player_map().values()

    # TODO: break ties with points ratio, head-to-head, etc.!!!
    sort_key = lambda x: (-x.seed_win_pct, -x.seed_pts_diff, -x.seed_pts_pct)
    for i, player in enumerate(sorted(pl_list, key=sort_key)):
        player.player_seed = i + 1
        player.save()

    TournInfo.mark_stage_complete(TournStage.SEED_RANKS)

def fake_picking_partners() -> None:
    """
    """
    pl_list = Player.get_player_map().values()
    by_seed = sorted(pl_list, key=lambda x: x.player_seed)

    # highest seeded champ must pick fellow champ(s)
    champs = [p for p in by_seed if p.reigning_champ]
    champs[0].pick_partners(*champs[1:])
    for p in champs:
        by_seed.remove(p)

    # non-champs pick randomly
    avail = list(by_seed)  # shallow copy (no champs)
    for player in by_seed:
        player_num = player.player_num
        if player.picked_by:
            assert player not in avail
            continue
        avail.remove(player)

        partners = [random.choice(avail)]
        avail.remove(partners[0])
        if len(avail) == 1:  # three-headed monster
            partners.append(avail.pop(0))
        player.pick_partners(*partners)
    assert len(avail) == 0

    for player in pl_list:
        player.save()

    TournInfo.mark_stage_complete(TournStage.PARTNER_PICK)

def build_tourn_teams() -> list[Team]:
    """
    """
    pl_map = Player.get_player_map()
    by_seed = sorted(pl_map.values(), key=lambda x: x.player_seed)

    teams = []
    for p in by_seed:
        if not p.partner_num:
            continue
        partner = pl_map[p.partner_num]
        seed_sum = p.player_seed + partner.player_seed
        min_seed = min(p.player_seed, partner.player_seed)
        if not p.partner2_num:
            is_thm = False
            team_name = fmt_team_name([p.player_num, p.partner_num])
            avg_seed = seed_sum / 2.0
        else:
            partner2 = pl_map[p.partner2_num]
            is_thm = True
            team_name = fmt_team_name([p.player_num, p.partner_num, p.partner2_num])
            seed_sum += partner2.player_seed
            min_seed = min(min_seed, partner2.player_seed)
            avg_seed = seed_sum / 3.0

        info = {'player1_num'    : p.player_num,
                'player2_num'    : p.partner_num,
                'player3_num'    : p.partner2_num,
                'is_thm'         : is_thm,
                'team_name'      : team_name,
                'avg_player_seed': avg_seed,
                'top_player_seed': min_seed}
        team = Team.create(**info)
        teams.append(team)

    TournInfo.mark_stage_complete(TournStage.TOURN_TEAMS)
    return teams

def compute_team_seeds() -> None:
    """
    """
    tm_iter = Team.iter_teams()
    tourn = TournInfo.get()
    ndivs = tourn.divisions

    sort_key = lambda x: (x.avg_player_seed, x.top_player_seed)
    for i, team in enumerate(sorted(tm_iter, key=sort_key)):
        team.team_seed = i + 1
        # REVISIT: see comment on seeds and preferential bye treatment below (in
        # `build_tourn_bracket`)
        team.div_num = i % ndivs + 1
        team.div_seed = i // ndivs + 1
        team.save()

    tourn.complete_stage(TournStage.TEAM_SEEDS)

def build_tourn_bracket() -> list[TournGame]:
    """
    """
    tm_map = Team.get_team_map()
    tourn = TournInfo.get()
    nteams = tourn.teams
    ndivs = tourn.divisions
    nrounds = tourn.tourn_rounds
    bye_seed = nteams + 1  # below all others

    # lower numbered divisions may have one extra team--REVISIT: this is probably wrong,
    # since the highest seeded overall team (div 1, seed 1) should have preferemtial bye
    # over all other division top seeds!!!
    div_teams = [nteams // ndivs] * ndivs
    div_mod = nteams % ndivs
    for i in range(div_mod):
        div_teams[i - ndivs] += 1
    assert sum(div_teams) == nteams

    games = []
    for div_i in range(ndivs):
        brckt_teams = div_teams[div_i]
        bye_div_seed = brckt_teams + 1  # TODO: only if odd number of teams!!!
        bracket_file = f'rr-{brckt_teams}-{nrounds}.csv'
        div_map = Team.get_div_map(div_i + 1)
        with open(DataFile(bracket_file), newline='') as f:
            reader = csv.reader(f)
            for rnd_j, row in enumerate(reader):
                seats = (int(x) for x in row)
                tbl_k = 0
                while table := list(islice(seats, 0, 2)):
                    if bye_div_seed in table:
                        t1, t2 = sorted(table)
                        assert t2 == bye_div_seed
                        label = f'rr-d{div_i+1}-r{rnd_j+1}-bye'
                        team1 = div_map[t1]
                        info = {'div_num'       : div_i + 1,
                                'round_num'     : rnd_j + 1,
                                'table_num'     : None,
                                'label'         : label,
                                'team1'         : team1,
                                'team2'         : None,
                                'team1_name'    : team1.team_name,
                                'team2_name'    : BYE_TEAM,
                                'team1_div_seed': team1.div_seed,
                                'team2_div_seed': None}
                    else:
                        t1,t2 = table
                        label = f'rr-d{div_i+1}-r{rnd_j+1}-t{tbl_k+1}'
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
                                'team1_div_seed': team1.div_seed,
                                'team2_div_seed': team2.div_seed}
                        tbl_k += 1
                    game = TournGame.create(**info)
                    games.append(game)

    tourn.complete_stage(TournStage.TOURN_BRACKET)
    return games

def fake_tourn_games() -> None:
    """Generates random team points and determines winner for each tournament game (before
    semis/finals)
    """
    for game in TournGame.iter_games():
        winner_pts = 10
        loser_pts = random.randrange(10)
        if random.randrange(2) > 0:
            game.add_scores(winner_pts, loser_pts)
        else:
            game.add_scores(loser_pts, winner_pts)
        game.save()

    TournInfo.mark_stage_complete(TournStage.TOURN_RESULTS)

def tabulate_tourn() -> None:
    """
    """
    tm_map = Team.get_team_map()

    for team in tm_map.values():
        assert team.tourn_wins is None
        assert team.tourn_losses is None
        assert team.tourn_pts_for is None
        assert team.tourn_pts_against is None
        team.tourn_wins = 0
        team.tourn_losses = 0
        team.tourn_pts_for = 0
        team.tourn_pts_against = 0

    for game in TournGame.iter_games():
        team1 = tm_map[game.team1_seed]
        team2 = tm_map[game.team2_seed]

        if game.winner == game.team1_name:
            team1.tourn_wins += 1
            team2.tourn_losses += 1
        else:
            team1.tourn_losses += 1
            team2.tourn_wins += 1

        team1.tourn_pts_for += game.team1_pts
        team2.tourn_pts_for += game.team2_pts
        team1.tourn_pts_against += game.team2_pts
        team2.tourn_pts_against += game.team1_pts

    for team in tm_map.values():
        ngames = team.tourn_wins + team.tourn_losses
        totpts = team.tourn_pts_for + team.tourn_pts_against
        team.tourn_win_pct = team.tourn_wins / ngames * 100.0
        team.tourn_pts_diff = team.tourn_pts_for - team.tourn_pts_against
        team.tourn_pts_pct = team.tourn_pts_for / totpts * 100.0
        team.save()

    TournInfo.mark_stage_complete(TournStage.TOURN_TABULATE)

def compute_team_ranks() -> None:
    """
    """
    tourn = TournInfo.get()
    ndivs = tourn.divisions
    tm_list = Team.get_team_map().values()

    div_rank = {i + 1: 0 for i in range(ndivs)}
    # TODO: break ties with points ratio, head-to-head, etc.!!!
    sort_key = lambda x: (-x.tourn_win_pct, -x.tourn_pts_diff, -x.tourn_pts_pct)
    for i, team in enumerate(sorted(tm_list, key=sort_key)):
        team.tourn_rank = i + 1
        div_rank[team.div_num] += 1
        team.div_rank = div_rank[team.div_num]
        team.save()

    tourn.complete_stage(TournStage.TEAM_RANKS)

########
# main #
########

import sys

from ckautils import parse_argv

def main() -> int:
    """Built-in driver to invoke module functions

    Usage: python -m euchmgr <tourn_name> <func> [<args> ...]

    Functions/usage:
      - tourn_create [timeframe=<timeframe>] [venue=<venue>] [<schema_create kwargs>]
      - upload_roster roster=<csv_file>
      - generate_player_nums
      - build_seed_bracket
      - fake_seed_games
      - tabulate_seed_round
      - compute_player_seeds
      - fake_picking_partners
      - build_tourn_teams
      - compute_team_seeds
      - build_tourn_bracket
      - fake_tourn_games
      - tabulate_tourn
      - compute_team_ranks
    """
    if len(sys.argv) < 2:
        print(main.__doc__)
        print(f"Tournament name not specified", file=sys.stderr)
        return -1
    if len(sys.argv) < 3:
        print(main.__doc__)
        print(f"Module function not specified", file=sys.stderr)
        return -1
    elif sys.argv[2] not in globals():
        print(f"Unknown module function '{sys.argv[2]}'", file=sys.stderr)
        return -1

    tourn_name = sys.argv[1]
    util_func = globals()[sys.argv[2]]
    args, kwargs = parse_argv(sys.argv[3:])

    db_init(tourn_name)
    util_func(*args, **kwargs)  # will throw exceptions on error
    return 0

if __name__ == '__main__':
    sys.exit(main())
