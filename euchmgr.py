#!/usr/bin/env python
# -*- coding: utf-8 -*-

import random
import csv
import os

from database import db_init
from schema import schema_create, TournInfo, Player

def tourn_create(name: str, date_info: str = None, venue: str = None, **kwargs) -> None:
    """Create a tournament with specified name (must be unique).

    additional `kwargs` passed on to `schema_create`
    """
    db_init(name)
    schema_create(**kwargs)

    info = {'name'     : name,
            'date_info': date_info,
            'venue'    : venue}
    tourn_info = TournInfo.create(**info)

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

    thm_teams = int(nchamps == 3)
    non_champs = nplayers - nchamps
    if non_champs & 0x01:
        thm_teams += 1
    nteams = non_champs // 2 + 1
    assert nteams == (nplayers - thm_teams) // 2

    tourn_info = TournInfo.get(TournInfo.name == name)
    tourn_info.players = nplayers
    tourn_info.teams = nteams
    tourn_info.thm_teams = thm_teams
    tourn_info.save()

def build_seed_backet(name: str) -> None:
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

    Usage: python -m euchmgr <func> [<args> ...]

    Functions/usage:
      - tourn_create <name> [date_info=<date_info>] [venue=<venue>]
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
