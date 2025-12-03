#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This module contains the core logic for managing Beta-style euchre tournaments, coupled
with encapsulated database logic in schema.py.  The interfaces/interactions are still kind
of messy in some places (and may end up staying that way, oh well...).

The To Do List has been moved to TODO.md.
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

def get_div_teams(tourn: TournInfo, requery: bool = False) -> list[int]:
    """Return number of teams by division, where index is `div_num - 1` (not pretty, but a
    little more expeditious)
    """
    div_teams = [0] * tourn.divisions
    for tm in Team.get_team_map(requery=requery).values():
        div_teams[tm.div_num - 1] += 1
    assert sum(div_teams) == tourn.teams
    assert max(div_teams) - min(div_teams) in (0, 1)
    return div_teams

# REVISIT: these functions should probably be moved into schema.py, and the denormalized
# values for player and team names should be created upon record save!!!

def fmt_player_list(player_nums: list[int]) -> str:
    """Consistently delimited list of player names, e.g. byes for a round
    """
    pl_map = Player.get_player_map()
    nick_names = [pl_map[p].nick_name for p in player_nums]
    return ', '.join(nick_names)

def fmt_team_name(player_nums: list[int]) -> str:
    """Consistent concatenation of member player names
    """
    pl_map = Player.get_player_map()
    nick_names = [pl_map[p].nick_name for p in player_nums]
    return ' / '.join(nick_names)

# good enough floating point equivalence
equiv = lambda x, y: round(x, 2) == round(y, 2)

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
    # for now we just clear existing values (if needed), so we don't have to test and/or
    # work around contiguousness
    Player.clear_player_nums()

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

    Note: we should probably move the construction of denorm columns (team names and byes)
    into schema.py (save())--see comment for utility functions, above
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
                    label = f'seed-{rnd_i+1}-byes'
                    team1_name = team2_name = None
                else:
                    p1, p2, p3, p4 = table
                    table_num = tbl_j + 1
                    label = f'seed-{rnd_i+1}-{tbl_j+1}'
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
                tbl_j += 1
                game = SeedGame.create(**info)
                games.append(game)
                if game.bye_players:
                    game.insert_player_games()

    tourn.complete_stage(TournStage.SEED_BRACKET)
    return games

def fake_seed_games(clear_existing: bool = False, limit: int = None) -> None:
    """Generates random team points and determines winner for each seed game.  Note that
    `clear_existing` only clears completed games.
    """
    nfake = 0
    sort_key = lambda x: (x.round_num, x.table_num)
    for game in sorted(SeedGame.iter_games(), key=sort_key):
        if game.winner and not clear_existing:
            continue
        winner_pts = 10
        loser_pts = random.randrange(10)
        if random.randrange(2) > 0:
            game.add_scores(winner_pts, loser_pts)
        else:
            game.add_scores(loser_pts, winner_pts)
        game.save()
        if limit:
            print(f"{game.team1_name}: {game.team1_pts}, {game.team2_name}: {game.team2_pts}")

        if game.winner:
            game.update_player_stats()
            game.insert_player_games()

        nfake += 1
        if limit and nfake >= limit:
            compute_player_ranks()
            return

    if limit and nfake and nfake < limit:
        compute_player_ranks()

    TournInfo.mark_stage_complete(TournStage.SEED_RESULTS)

def validate_seed_round(finalize: bool = False) -> None:
    """
    """
    pl_map = Player.get_player_map(requery=True)

    stats_tmpl = {
        'seed_wins':        0,
        'seed_losses':      0,
        'seed_pts_for':     0,
        'seed_pts_against': 0
    }
    pl_stats = {num: stats_tmpl.copy() for num in pl_map}

    for gm in SeedGame.iter_games():
        stats1 = pl_stats[gm.player1_num]
        stats2 = pl_stats[gm.player2_num]
        stats3 = pl_stats[gm.player3_num]
        stats4 = pl_stats[gm.player4_num]

        if gm.winner == gm.team1_name:
            stats1['seed_wins'] += 1
            stats2['seed_wins'] += 1
            stats3['seed_losses'] += 1
            stats4['seed_losses'] += 1
        else:
            stats1['seed_losses'] += 1
            stats2['seed_losses'] += 1
            stats3['seed_wins'] += 1
            stats4['seed_wins'] += 1

        stats1['seed_pts_for'] += gm.team1_pts
        stats2['seed_pts_for'] += gm.team1_pts
        stats3['seed_pts_for'] += gm.team2_pts
        stats4['seed_pts_for'] += gm.team2_pts
        stats1['seed_pts_against'] += gm.team2_pts
        stats2['seed_pts_against'] += gm.team2_pts
        stats3['seed_pts_against'] += gm.team1_pts
        stats4['seed_pts_against'] += gm.team1_pts

    stats_tot = stats_tmpl.copy()
    for num, pl in pl_map.items():
        stats = pl_stats[num]
        for k, v in stats.items():
            stats_tot[k] += v

        assert pl.seed_wins        == stats['seed_wins']
        assert pl.seed_losses      == stats['seed_losses']
        assert pl.seed_pts_for     == stats['seed_pts_for']
        assert pl.seed_pts_against == stats['seed_pts_against']

        ngames   = stats['seed_wins'] + stats['seed_losses']
        win_pct  = stats['seed_wins'] / ngames * 100.0
        pts_tot  = stats['seed_pts_for'] + stats['seed_pts_against']
        pts_diff = stats['seed_pts_for'] - stats['seed_pts_against']
        pts_pct  = stats['seed_pts_for'] / pts_tot * 100.0

        assert equiv(pl.seed_win_pct, win_pct)
        assert pl.seed_pts_diff == pts_diff
        assert equiv(pl.seed_pts_pct, pts_pct)

    assert stats_tot['seed_wins'] == stats_tot['seed_losses']
    assert stats_tot['seed_pts_for'] == stats_tot['seed_pts_against']

    if finalize:
        TournInfo.mark_stage_complete(TournStage.SEED_TABULATE)

def compute_player_ranks(finalize: bool = False) -> None:
    """
    """
    pl_list = Player.get_player_map().values()
    played = filter(lambda x: x.seed_wins + x.seed_losses, pl_list)

    # TODO: break ties with points ratio, head-to-head, etc.!!!
    sort_key = lambda x: (-x.seed_win_pct, -x.seed_pts_pct)
    for i, player in enumerate(sorted(played, key=sort_key)):
        player.player_rank = i + 1
        player.save()

    if finalize:
        TournInfo.mark_stage_complete(TournStage.SEED_RANKS)

def prepick_champ_partners() -> None:
    """Reigning champs get paired (or tripled) as a team before general partner picking
    starts
    """
    pl_list = Player.get_player_map().values()
    champs = filter(lambda x: x.reigning_champ, pl_list)
    by_rank = sorted(champs, key=lambda x: x.player_rank)

    # highest seeded champ picks fellow champ(s)
    assert len(by_rank) in (2, 3)
    by_rank[0].pick_partners(*by_rank[1:])
    by_rank[0].save()

def fake_pick_partners(clear_existing: bool = False) -> None:
    """Assumes champ team is pre-picked
    """
    if clear_existing:
        Player.clear_partner_picks()

    avail = Player.available_players()  # already sorted by player_rank
    assert len(avail) >= 2
    pickers = list(avail)  # shallow copy
    for player in pickers:
        # picker may have already been picked in this loop
        if player.picked_by:
            assert player not in avail
            continue
        avail.remove(player)

        partners = [random.choice(avail)]
        avail.remove(partners[0])
        if len(avail) == 1:  # three-headed monster
            partners.append(avail.pop(0))
        player.pick_partners(*partners)
        player.save()
    assert len(avail) == 0

    TournInfo.mark_stage_complete(TournStage.PARTNER_PICK)

def build_tourn_teams() -> list[Team]:
    """Note: we should probably move the construction of the team name into schema.py
    (save())--see comment for utility functions, above
    """
    pl_map = Player.get_player_map()
    by_rank = sorted(pl_map.values(), key=lambda x: x.player_rank)

    teams = []
    for p in by_rank:
        if not p.partner_num:
            continue
        partner = pl_map[p.partner_num]
        seed_sum = p.player_rank + partner.player_rank
        min_seed = min(p.player_rank, partner.player_rank)
        if not p.partner2_num:
            is_thm = False
            team_name = fmt_team_name([p.player_num, p.partner_num])
            avg_seed = seed_sum / 2.0
        else:
            partner2 = pl_map[p.partner2_num]
            is_thm = True
            team_name = fmt_team_name([p.player_num, p.partner_num, p.partner2_num])
            seed_sum += partner2.player_rank
            min_seed = min(min_seed, partner2.player_rank)
            avg_seed = seed_sum / 3.0

        info = {'player1_num'    : p.player_num,
                'player2_num'    : p.partner_num,
                'player3_num'    : p.partner2_num,
                'is_thm'         : is_thm,
                'team_name'      : team_name,
                'avg_player_rank': avg_seed,
                'top_player_rank': min_seed}
        team = Team.create(**info)
        teams.append(team)

    TournInfo.mark_stage_complete(TournStage.TOURN_TEAMS)
    return teams

def compute_team_seeds() -> None:
    """
    """
    tm_list = list(Team.iter_teams())
    tourn = TournInfo.get()
    ndivs = tourn.divisions
    assert len(tm_list) == tourn.teams

    # we assign teams to divisions based on a snake pattern (1, 2, ..., ndivs, ndivs,
    # ndivs - 1, ...) by creating a mapping, where the mapped value encapsulates the
    # division and seed within the division (integer mod and quotient, respectively)
    map_size = ((tourn.teams - 1) // ndivs + 1) * ndivs
    seed_map = list(range(map_size))
    for s in seed_map[ndivs::ndivs*2]:
        seed_map[s:s+ndivs] = reversed(seed_map[s:s+ndivs])

    # note that non-champ THM is always sorted to last postion
    sort_key = lambda x: (x.is_thm and not x.is_champ, x.avg_player_rank, x.top_player_rank)
    for i, tm in enumerate(sorted(tm_list, key=sort_key)):
        tm.team_seed = i + 1
        tm.div_num = seed_map[i] % ndivs + 1
        tm.div_seed = seed_map[i] // ndivs + 1
        tm.save()

    tourn.complete_stage(TournStage.TEAM_SEEDS)

def build_tourn_bracket() -> list[TournGame]:
    """
    """
    tourn = TournInfo.get()
    ndivs = tourn.divisions
    nrounds = tourn.tourn_rounds

    # don't make assumptions on how divisions are assigned, just get the actual count of
    # teams in each division--ATTN: this is a little messy, but note that div_teams is
    # 0-based, whereas div_num is 1-based (see loop below for pseudo-explanation)!
    div_teams = get_div_teams(tourn)

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
                        label = f'rr-{div_i+1}-{rnd_j+1}-bye'
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
                        t1,t2 = table
                        label = f'rr-{div_i+1}-{rnd_j+1}-{tbl_k+1}'
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

def fake_tourn_games(clear_existing: bool = False, limit: int = None) -> None:
    """Generates random team points and determines winner for each tournament game (before
    semis/finals).  Note that `clear_existing` only clears completed games.
    """
    nfake = 0
    sort_key = lambda x: (x.round_num, x.table_num)
    for game in sorted(TournGame.iter_games(), key=sort_key):
        if game.winner and not clear_existing:
            continue
        winner_pts = 10
        loser_pts = random.randrange(10)
        if random.randrange(2) > 0:
            game.add_scores(winner_pts, loser_pts)
        else:
            game.add_scores(loser_pts, winner_pts)
        game.save()
        if limit:
            print(f"{game.team1_name}: {game.team1_pts}, {game.team2_name}: {game.team2_pts}")

        if game.winner:
            game.update_team_stats()
            game.insert_team_games()

        nfake += 1
        if limit and nfake >= limit:
            compute_team_ranks()
            return

    if limit and nfake and nfake < limit:
        compute_team_ranks()

    TournInfo.mark_stage_complete(TournStage.TOURN_RESULTS)

def validate_tourn(finalize: bool = False) -> None:
    """
    """
    tm_map = Team.get_team_map(requery=True)

    stats_tmpl = {
        'tourn_wins':        0,
        'tourn_losses':      0,
        'tourn_pts_for':     0,
        'tourn_pts_against': 0
    }
    tm_stats = {seed: stats_tmpl.copy() for seed in tm_map}

    for gm in TournGame.iter_games():
        stats1 = tm_stats[gm.team1_seed]
        stats2 = tm_stats[gm.team2_seed]

        if gm.winner == gm.team1_name:
            stats1['tourn_wins'] += 1
            stats2['tourn_losses'] += 1
        else:
            stats1['tourn_losses'] += 1
            stats2['tourn_wins'] += 1

        stats1['tourn_pts_for'] += gm.team1_pts
        stats2['tourn_pts_for'] += gm.team2_pts
        stats1['tourn_pts_against'] += gm.team2_pts
        stats2['tourn_pts_against'] += gm.team1_pts

    stats_tot = stats_tmpl.copy()
    for seed, tm in tm_map.items():
        stats = tm_stats[seed]
        for k, v in stats.items():
            stats_tot[k] += v

        assert tm.tourn_wins        == stats['tourn_wins']
        assert tm.tourn_losses      == stats['tourn_losses']
        assert tm.tourn_pts_for     == stats['tourn_pts_for']
        assert tm.tourn_pts_against == stats['tourn_pts_against']

        ngames   = stats['tourn_wins'] + stats['tourn_losses']
        win_pct  = stats['tourn_wins'] / ngames * 100.0
        pts_tot  = stats['tourn_pts_for'] + stats['tourn_pts_against']
        pts_diff = stats['tourn_pts_for'] - stats['tourn_pts_against']
        pts_pct  = stats['tourn_pts_for'] / pts_tot * 100.0

        assert equiv(tm.tourn_win_pct, win_pct)
        assert tm.tourn_pts_diff == pts_diff
        assert equiv(tm.tourn_pts_pct, pts_pct)

    assert stats_tot['tourn_wins'] == stats_tot['tourn_losses']
    assert stats_tot['tourn_pts_for'] == stats_tot['tourn_pts_against']

    if finalize:
        TournInfo.mark_stage_complete(TournStage.TOURN_TABULATE)

def compute_team_ranks(finalize: bool = False) -> None:
    """
    """
    tourn = TournInfo.get()
    ndivs = tourn.divisions
    tm_list = Team.get_team_map().values()
    played = filter(lambda x: x.tourn_wins + x.tourn_losses, tm_list)

    div_rank = {i + 1: 0 for i in range(ndivs)}
    # TODO: break ties with points ratio, head-to-head, etc.!!!
    sort_key = lambda x: (-x.tourn_win_pct, -x.tourn_pts_pct)
    for i, team in enumerate(sorted(played, key=sort_key)):
        team.tourn_rank = i + 1
        div_rank[team.div_num] += 1
        team.div_rank = div_rank[team.div_num]
        team.save()

    if finalize:
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
      - compute_player_ranks
      - prepick_champ_partners
      - fake_pick_partners
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
