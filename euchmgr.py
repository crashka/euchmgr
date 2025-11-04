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
    """Populate seed round matchups and byes (in `seed_round` table) based on tournament
    parameters and uploaded roster.

    """
    db_init(name)
    tourn = TournInfo.get_by_name(name)
    bracket_file = f'seed-{tourn.players}-{tourn.seed_rounds}.csv'
    pl_map = Player.get_player_map()

    games = []
    with open(DataFile(bracket_file), newline='') as f:
        reader = csv.reader(f)
        for rnd_i, row in enumerate(reader):
            seats = (int(x) for x in row)
            tbl_j = 0
            while table := list(islice(seats, 0, 4)):
                if len(table) < 4:
                    bye_names = [pl_map[p].nick_name for p in table]
                    table += [None] * (4 - len(table))
                    p1, p2, p3, p4 = table
                    label = f'seed-r{rnd_i+1}-byes'
                    team1_name = team2_name = None
                    byes = ' / '.join(bye_names)
                else:
                    p1, p2, p3, p4 = table
                    label = f'seed-r{rnd_i+1}-t{tbl_j+1}'
                    team1_name = f'{pl_map[p1].nick_name} / {pl_map[p2].nick_name}'
                    team2_name = f'{pl_map[p3].nick_name} / {pl_map[p4].nick_name}'
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

def fake_seed_results(name: str) -> None:
    """
    """
    db_init(name)
    for game in SeedGame.select().where(SeedGame.byes.is_null()):
        if random.randrange(2) > 0:
            game.team1_pts = 10
            game.team2_pts = random.randrange(10)
            game.winner = game.team1_name
        else:
            game.team1_pts = random.randrange(10)
            game.team2_pts = 10
            game.winner = game.team2_name
        game.save()

def tabulate_seed_round(name: str) -> None:
    """
    """
    db_init(name)
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

def compute_player_seeds(name: str) -> None:
    """
    """
    db_init(name)
    pl_map = Player.get_player_map()

    # TODO: break ties with points ratio, head-to-head, etc.!!!
    sort_key = lambda x: (-x.seed_win_pct, -x.seed_pts_diff, -x.seed_pts_pct)
    by_record = sorted(pl_map.values(), key=sort_key)
    for i, player in enumerate(by_record):
        player.player_seed = i + 1
        player.save()

def fake_partner_picks(name: str) -> None:
    """NOTE: also builds Team records
    """
    db_init(name)
    pl_list = Player.get_player_map().values()
    by_seed = sorted(pl_list, key=lambda x: x.player_seed)

    # highest seeded champ must pick fellow champ(s)
    champs = [p for p in by_seed if p.reigning_champ]
    champ1 = champs.pop(0)
    print(f"champ: {champ1.player_num} ({champ1.nick_name})")
    by_seed.remove(champ1)
    assert len(champs) > 0

    champ2 = champs.pop(0)
    print(f"  - picks partner {champ2.player_num}")
    champ1.partner_num = champ2.player_num
    champ2.picked_by_num = champ1.player_num
    by_seed.remove(champ2)

    if len(champs) > 0:
        champ3 = champs.pop(0)
        print(f"  - picks partner {champ3.player_num}")
        champ1.partner2_num = champ3.player_num
        champ3.picked_by_num = champ1.player_num
        by_seed.remove(champ3)
    assert len(champs) == 0

    # non-champs pick randomly
    avail = list(by_seed)  # shallow copy (no champs)
    for player in by_seed:
        player_num = player.player_num
        print(f"player: {player_num} ({player.nick_name})")
        if player.picked_by:
            assert player not in avail
            print(f"  - already picked by {player.picked_by_num}, skipping...")
            continue
        avail.remove(player)

        partner = random.choice(avail)
        print(f"  - picks partner {partner.player_num}")
        player.partner_num = partner.player_num
        partner.picked_by_num = player_num
        avail.remove(partner)

        if len(avail) == 1:
            partner2 = avail.pop(0)
            print(f"  - picks partner {partner2.player_num}")
            player.partner2_num = partner2.player_num
            partner2.picked_by_num = player_num
            # note that we let it keep looping, for integrity checking
    assert len(avail) == 0

    for player in pl_list:
        player.save()

def build_tourn_bracket(name: str) -> None:
    """
    """
    pass

def fake_tourn_results(name: str) -> None:
    """
    """
    pass

def tabulate_tourn(name: str) -> None:
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
