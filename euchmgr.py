#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random
from itertools import islice
import csv
import os

from core import DataFile
from database import db_init, db_name
from schema import schema_create, TournInfo, Player, SeedGame

def tourn_create(timeframe: str = None, venue: str = None, **kwargs) -> None:
    """Create a tournament with specified name (must be unique).

    Additional `kwargs` are passed on to `schema_create`
    """
    schema_create(**kwargs)

    info = {'name'     : db_name(),  # db_name is same as tournament name
            'timeframe': timeframe,
            'venue'    : venue}
    tourn = TournInfo.create(**info)

def upload_roster(csv_path: str) -> None:
    """Create all Player records based on specified roster file (csv).  The header row
    must specify the required info field names for the model object.
    """
    players = []
    with open(csv_path, newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            player_info = dict(zip(header, row))
            player = Player(**player_info)
            players.append(player)

    # assign random numbers to players before saving (akin to picking ping pong balls out
    # of a bag)
    nplayers = len(players)
    ords = iter(random.sample(range(nplayers), nplayers))
    nchamps = 0
    for player in players:
        player.player_num = next(ords) + 1
        player.save()
        if player.reigning_champ:
            nchamps += 1

    # update tournament info (players, teams, etc.)
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
    tourn.save()

def team_name(player_nums: list[int]) -> str:
    """
    """
    pl_map = Player.get_player_map()
    nick_names = [pl_map[p].nick_name for p in player_nums]
    return ' / '.join(nick_names)

def build_seed_bracket() -> None:
    """Populate seed round matchups and byes (in `seed_round` table) based on tournament
    parameters and uploaded roster.

    """
    tourn = TournInfo.get()
    bracket_file = f'seed-{tourn.players}-{tourn.seed_rounds}.csv'

    games = []
    with open(DataFile(bracket_file), newline='') as f:
        reader = csv.reader(f)
        for rnd_i, row in enumerate(reader):
            seats = (int(x) for x in row)
            tbl_j = 0
            while table := list(islice(seats, 0, 4)):
                if len(table) < 4:
                    byes = team_name(table)
                    table += [None] * (4 - len(table))
                    p1, p2, p3, p4 = table
                    label = f'seed-r{rnd_i+1}-byes'
                    team1_name = team2_name = None
                else:
                    p1, p2, p3, p4 = table
                    label = f'seed-r{rnd_i+1}-t{tbl_j+1}'
                    team1_name = team_name([p1, p2])
                    team2_name = team_name([p3, p4])
                    byes = None
                info = {'round_num'  : rnd_i + 1,
                        'table_num'  : tbl_j + 1,
                        'label'      : label,
                        'player1_num': p1,
                        'player2_num': p2,
                        'player3_num': p3,
                        'player4_num': p4,
                        'team1_name' : team1_name,
                        'team2_name' : team2_name,
                        'byes'       : byes}
                game = SeedGame.create(**info)
                games.append(game)
                tbl_j += 1

def fake_seed_results() -> None:
    """Generates random team points and determines winner for each seed game
    """
    for game in SeedGame.select().where(SeedGame.byes.is_null()):
        winner_pts = 10
        loser_pts = random.randrange(10)
        if random.randrange(2) > 0:
            game.add_scores(winner_pts, loser_pts)
        else:
            game.add_scores(loser_pts, winner_pts)
        game.save()

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

    for game in SeedGame.select().where(SeedGame.byes.is_null()):
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

def compute_player_seeds() -> None:
    """
    """
    pl_list = Player.get_player_map().values()

    # TODO: break ties with points ratio, head-to-head, etc.!!!
    sort_key = lambda x: (-x.seed_win_pct, -x.seed_pts_diff, -x.seed_pts_pct)
    by_record = sorted(pl_list, key=sort_key)
    for i, player in enumerate(by_record):
        player.player_seed = i + 1
        player.save()

def fake_partner_picks() -> None:
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

def build_tourn_teams() -> None:
    """
    """
    pl_list = Player.get_player_map().values()
    by_seed = sorted(pl_list, key=lambda x: x.player_seed)

def build_tourn_bracket() -> None:
    """
    """
    pass

def fake_tourn_results() -> None:
    """
    """
    pass

def tabulate_tourn() -> None:
    """
    """
    pass

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
      - build_seed_bracket
      - fake_seed_results
      - tabulate_seed_round
      - compute_player_seeds
      - fake_partner_picks
      - build_tourn_teams
      - build_tourn_brackets
      - fake_tourn_results
      - tabulate_tourn
    """
    if len(sys.argv) < 2:
        print(f"Tournament name not specified", file=sys.stderr)
        return -1
    if len(sys.argv) < 3:
        print(f"Utility function not specified", file=sys.stderr)
        return -1
    elif sys.argv[2] not in globals():
        print(f"Unknown utility function '{sys.argv[2]}'", file=sys.stderr)
        return -1

    tourn_name = sys.argv[1]
    util_func = globals()[sys.argv[2]]
    args, kwargs = parse_argv(sys.argv[3:])

    db_init(tourn_name)
    return util_func(*args, **kwargs)

if __name__ == '__main__':
    sys.exit(main())
