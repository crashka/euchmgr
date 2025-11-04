#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random
from itertools import islice
import csv
import os

from core import DataFile
from database import db_init
from schema import schema_create, TournInfo, Player, SeedGame

def tourn_create(name: str, timeframe: str = None, venue: str = None, **kwargs) -> None:
    """Create a tournament with specified name (must be unique).

    additional `kwargs` passed on to `schema_create`
    """
    db_init(name)
    schema_create(**kwargs)

    info = {'name'     : name,
            'timeframe': timeframe,
            'venue'    : venue}
    tourn = TournInfo.create(**info)

def upload_roster(name: str, path: str) -> None:
    """Create all Player records based on specified roster file (csv).  The header row
    must specify the required info field names for the model object.
    """
    db_init(name)
    players = []
    with open(path, newline='') as f:
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

    tourn = TournInfo.get_by_name(name)
    tourn.players = nplayers
    tourn.teams = nteams
    tourn.thm_teams = thm_teams
    tourn.save()

def build_seed_bracket(name: str) -> None:
    """
    """
    db_init(name)
    tourn = TournInfo.get_by_name(name)
    bracket_file = f'seed-{tourn.players}-{tourn.seed_rounds}.csv'
    players = Player.dict_by_num()

    games = []
    with open(DataFile(bracket_file), newline='') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            seats = (int(x) for x in row)
            j = 0
            while table := list(islice(seats, 0, 4)):
                if len(table) < 4:
                    byes = [players[p].nick_name for p in table]
                    table += [None] * (4 - len(table))
                    p1, p2, p3, p4 = table
                    label = f'seed-r{i+1}-byes'
                    team1_name = team2_name = None
                    bye_names = ' / '.join(byes)
                else:
                    p1, p2, p3, p4 = table
                    label = f'seed-r{i+1}-t{j+1}'
                    team1_name = f'{players[p1].nick_name} / {players[p2].nick_name}'
                    team2_name = f'{players[p3].nick_name} / {players[p4].nick_name}'
                    bye_names = None
                info = {'round_num'  : i + 1,
                        'table_num'  : j + 1,
                        'label'      : label,
                        'player1_num': p1,
                        'player2_num': p2,
                        'player3_num': p3,
                        'player4_num': p4,
                        'team1_name' : team1_name,
                        'team2_name' : team2_name,
                        'byes'       : bye_names}
                game = SeedGame.create(**info)
                games.append(game)
                j += 1

########
# main #
########

import sys

from ckautils import parse_argv

def main() -> int:
    """Built-in driver to invoke module functions

    Usage: python -m euchmgr <func> [<args> ...]

    Functions/usage:
      - tourn_create <name> [timeframe=<timeframe>] [venue=<venue>]
      - upload_roster <name> <file>
    """
    if len(sys.argv) < 2:
        print(f"Utility function not specified", file=sys.stderr)
        return -1
    elif sys.argv[1] not in globals():
        print(f"Unknown utility function '{sys.argv[1]}'", file=sys.stderr)
        return -1

    util_func = globals()[sys.argv[1]]
    args, kwargs = parse_argv(sys.argv[2:])

    return util_func(*args, **kwargs)

if __name__ == '__main__':
    sys.exit(main())
