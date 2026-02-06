#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This module contains the core logic for managing Beta-style euchre tournaments, coupled
with encapsulated database logic in schema.py.  The interfaces/interactions are still kind
of messy in some places (and may end up staying that way, oh well...).

The To Do List has been moved to TODO.md.
"""

import random
from itertools import islice, groupby
import csv
import os

from ckautils import rankdata

from core import BracketsFile, DEBUG, log
from database import db_init, db_close, db_name
from schema import (rnd_pct, rnd_avg, Bracket, TournStage, TournInfo, Player, SeedGame,
                    Team, TournGame, PlayoffGame, schema_create)

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

def get_bracket(label: str) -> str:
    """Get bracket for the specified game label.  FIX: quick and dirty for now--need a
    proper representations of bracket definitions overall!!!
    """
    pfx = label.split('-', 1)[0]
    assert pfx in (Bracket.SEED, Bracket.TOURN)
    return pfx

def get_game_by_label(label: str) -> SeedGame | TournGame:
    """Use a little ORM knowledge to fetch from the appropriate table--LATER: can put this
    in the right place (or refactor the whole bracket-game thing)!!!
    """
    game_cls = SeedGame if get_bracket(label) == Bracket.SEED else TournGame
    query = (game_cls
             .select()
             .where(game_cls.label == label))
    return query.get_or_none()

#####################
# euchmgr functions #
#####################

def tourn_create(force: bool = False, **tourn_attrs) -> TournInfo:
    """Create a tournament with its name specified by the currently-connected database
    name (this is a little bit of a cheat to make the __main__ script for this module
    work).  The `force` flag is passed on to the `schema_create` call.  `tourn_attrs`
    represents the optional fields for the TournInfo record.
    """
    schema_create(force=force)

    info = {'name'        : db_name(),  # see docheader
            'dates'       : tourn_attrs.get('dates'),
            'venue'       : tourn_attrs.get('venue'),
            'dflt_pw_hash': tourn_attrs.get('dflt_pw_hash'),
            'stage_compl' : TournStage.TOURN_CREATE}
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

def generate_player_nums(rand_seed: int = None, limit: int = None) -> None:
    """Generate random values for player_num, akin to picking numbered ping pong balls out
     of a bag.

    Note: player_nums can also be specified in the roster file or manually assigned, which
    in either case this function will fill in the remaining empty player_nums randomly
    with unused values.
    """
    my_rand = random.Random()
    if isinstance(rand_seed, int):
        my_rand.seed(rand_seed)  # for reproducible debugging only

    pl_list = list(Player.iter_players(no_nums=True))
    ords = iter(my_rand.sample(Player.nums_avail(), len(pl_list)))
    for i, player in enumerate(pl_list):
        if limit and i >= limit:
            break
        player.player_num = next(ords)
        player.save()

    if len(Player.nums_avail()) == 0:
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
    bracket_file = f'seed-{nplayers}-{nrounds}.csv'  # need to reconcile with Bracket.SEED!!!

    games = []
    with open(BracketsFile(bracket_file), newline='') as f:
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
                    label = f'{Bracket.SEED}-{rnd_i+1}-byes'
                    team1_name = team2_name = None
                else:
                    p1, p2, p3, p4 = table
                    table_num = tbl_j + 1
                    label = f'{Bracket.SEED}-{rnd_i+1}-{tbl_j+1}'
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

def fake_seed_games(clear_existing: bool = False, limit: int = None, rand_seed: int = None) -> None:
    """Generates random team points and determines winner for each seed game.  Note that
    `clear_existing` only clears completed games.
    """
    my_rand = random.Random()
    if isinstance(rand_seed, int):
        my_rand.seed(rand_seed)  # for reproducible debugging only

    nfake = 0
    sort_key = lambda x: (x.round_num, x.table_num)
    for game in sorted(SeedGame.iter_games(), key=sort_key):
        if game.winner and not clear_existing:
            continue
        winner_pts = 10
        loser_pts = my_rand.randrange(10)
        if my_rand.randrange(2) > 0:
            game.add_scores(winner_pts, loser_pts)
        else:
            game.add_scores(loser_pts, winner_pts)
        game.save()
        if limit and DEBUG:
            log.debug(f"{game.team1_name}: {game.team1_pts}, {game.team2_name}: {game.team2_pts}")

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

        ngames  = stats['seed_wins'] + stats['seed_losses']
        win_pct = rnd_pct(stats['seed_wins'] / ngames)
        pts_tot = stats['seed_pts_for'] + stats['seed_pts_against']
        pts_pct = rnd_pct(stats['seed_pts_for'] / pts_tot)

        # note that floating point values should have been similarly rounded, so using
        # `==` should be robust (for equivalence) as well as help validate consistent
        # rounding in code
        assert pl.seed_win_pct == win_pct
        assert pl.seed_pts_pct == pts_pct

    assert stats_tot['seed_wins'] == stats_tot['seed_losses']
    assert stats_tot['seed_pts_for'] == stats_tot['seed_pts_against']

    if finalize:
        TournInfo.mark_stage_complete(TournStage.SEED_TABULATE)

def rank_player_cohort(players: list[Player]) -> list[tuple[Player, tuple, dict]]:
    """Given a list of players (generally with the same record, though we are not checking
    here, since we don't really care), return list ranked by the following stats tuple:

      (seed_pts_pct,)

    The `data` dict (last return element) is no longer used for the seeding round.
    """
    # larger is better for all stats components
    sort_key = lambda x: (-x.seed_pts_pct,)
    ranked = sorted(players, key=sort_key)
    return [(pl, (pl.seed_pts_pct,), None) for pl in ranked]

def compute_player_ranks(finalize: bool = False) -> None:
    """Note that we use `rankdata` to do the computation here, and `rank_player_cohort` to
    break ties.
    """
    pl_list = Player.get_player_map().values()
    played = list(filter(lambda x: x.seed_wins + x.seed_losses, pl_list))

    seed_win_pcts = [pl.seed_win_pct for pl in played]
    seed_ranks = rankdata(seed_win_pcts, method='min')
    for i, pl in enumerate(played):
        pl.player_pos = seed_ranks[i]

    # high-level ranking based on win percentage, before tie-breaking
    played.sort(key=lambda x: x.seed_win_pct, reverse=True)
    for k, g in groupby(played, key=lambda x: x.seed_win_pct):
        cohort = list(g)
        if len(cohort) == 1:
            pl = cohort[0]
            pl.player_rank = pl.player_pos
            pl.seed_tb_crit = None
            pl.seed_tb_data = None
            pl.save()
            continue
        cohort_pos = cohort[0].player_pos
        ranked = rank_player_cohort(cohort)
        for i, (pl, crit, data) in enumerate(ranked):
            pl.player_rank = cohort_pos + i
            pl.seed_tb_crit = crit
            pl.seed_tb_data = data
            pl.save()

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

def fake_pick_partners(clear_existing: bool = False, limit: int = None, rand_seed: int = None) -> None:
    """Assumes champ team is pre-picked
    """
    my_rand = random.Random()
    if isinstance(rand_seed, int):
        my_rand.seed(rand_seed)  # for reproducible debugging only

    if clear_existing:
        Player.clear_partner_picks()

    avail = Player.available_players()  # already sorted by player_rank
    assert len(avail) != 1
    nfake = 0
    pickers = list(avail)  # shallow copy
    for player in pickers:
        # picker may have already been picked in this loop
        if player.picked_by:
            assert player not in avail
            continue
        avail.remove(player)

        partners = [my_rand.choice(avail)]
        avail.remove(partners[0])
        if len(avail) == 1:  # three-headed monster
            partners.append(avail.pop(0))
        player.pick_partners(*partners)
        player.save()

        nfake += 1
        if limit and nfake >= limit:
            return
    assert len(avail) == 0

    TournInfo.mark_stage_complete(TournStage.PARTNER_PICK)

def build_tourn_teams() -> list[Team]:
    """Note: we should probably move the construction of the team name into schema.py
    (save())--see comment for utility functions, above
    """
    pl_map = Player.get_player_map()
    by_rank = sorted(pl_map.values(), key=lambda x: x.player_rank)

    teams = []
    for pl in by_rank:
        if not pl.partner_num:
            continue
        partner = pl_map[pl.partner_num]
        seed_sum = pl.player_rank + partner.player_rank
        min_seed = min(pl.player_rank, partner.player_rank)
        if not pl.partner2_num:
            partner2 = None
            is_thm = False
            team_name = fmt_team_name([pl.player_num, pl.partner_num])
            avg_seed = rnd_avg(seed_sum / 2.0)
        else:
            partner2 = pl_map[pl.partner2_num]
            is_thm = True
            team_name = fmt_team_name([pl.player_num, pl.partner_num, pl.partner2_num])
            seed_sum += partner2.player_rank
            min_seed = min(min_seed, partner2.player_rank)
            avg_seed = rnd_avg(seed_sum / 3.0)

        info = {'player1'        : pl,
                'player2'        : partner,
                'player3'        : partner2,
                'is_thm'         : is_thm,
                'team_name'      : team_name,
                'avg_player_rank': avg_seed,
                'top_player_rank': min_seed}
        team = Team.create(**info)
        team.save_team_refs()
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
        bracket_file = f'rr-{brckt_teams}-{nrounds}.csv'  # need to reconcile with Bracket.TOURN!!!
        div_map = Team.get_div_map(div_i + 1)
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

def fake_tourn_games(clear_existing: bool = False, limit: int = None, rand_seed: int = None) -> None:
    """Generates random team points and determines winner for each tournament game (before
    semis/finals).  Note that `clear_existing` only clears completed games.
    """
    my_rand = random.Random()
    if isinstance(rand_seed, int):
        my_rand.seed(rand_seed)  # for reproducible debugging only

    nfake = 0
    sort_key = lambda x: (x.round_num, x.table_num)
    for game in sorted(TournGame.iter_games(), key=sort_key):
        if game.winner and not clear_existing:
            continue
        winner_pts = 10
        loser_pts = my_rand.randrange(10)
        if my_rand.randrange(2) > 0:
            game.add_scores(winner_pts, loser_pts)
        else:
            game.add_scores(loser_pts, winner_pts)
        game.save()
        if limit and DEBUG:
            log.debug(f"{game.team1_name}: {game.team1_pts}, {game.team2_name}: {game.team2_pts}")

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
    tm_stats = {id: stats_tmpl.copy() for id in tm_map}

    for gm in TournGame.iter_games():
        stats1 = tm_stats[gm.team1_id]
        stats2 = tm_stats[gm.team2_id]

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
    for id, tm in tm_map.items():
        stats = tm_stats[id]
        for k, v in stats.items():
            stats_tot[k] += v

        assert tm.tourn_wins        == stats['tourn_wins']
        assert tm.tourn_losses      == stats['tourn_losses']
        assert tm.tourn_pts_for     == stats['tourn_pts_for']
        assert tm.tourn_pts_against == stats['tourn_pts_against']

        ngames  = stats['tourn_wins'] + stats['tourn_losses']
        win_pct = rnd_pct(stats['tourn_wins'] / ngames)
        pts_tot = stats['tourn_pts_for'] + stats['tourn_pts_against']
        pts_pct = rnd_pct(stats['tourn_pts_for'] / pts_tot)

        # see note about floating points and rounding in `validate_seed_round` (above)
        assert tm.tourn_win_pct == win_pct
        assert tm.tourn_pts_pct == pts_pct

    assert stats_tot['tourn_wins'] == stats_tot['tourn_losses']
    assert stats_tot['tourn_pts_for'] == stats_tot['tourn_pts_against']

    if finalize:
        TournInfo.mark_stage_complete(TournStage.TOURN_TABULATE)

def rank_tourn_cohort(teams: list[Team]) -> tuple[list[Team], dict[tuple], dict[dict]]:
    """Given a list of teams (generally with the same record, though we are not checking
    here, since we don't really care), return list of teams ranked by the following stats
    tuple:

      (tourn_pts_pct,)

    The other two return elements are the actual stats tuples and aggregated head-to-head
    game data for the cohort teams, both indexed by team seed.
    """
    stats = {}
    data = {}
    for tm in teams:
        stats[tm.team_seed] = (tm.tourn_pts_pct,)
        data[tm.team_seed] = {}

    # larger is better for all stats components
    sort_key = lambda tm: tuple(-x for x in stats[tm.team_seed])
    ranked = sorted(teams, key=sort_key)
    return ranked, stats, data

def rank_team_cohort(teams: list[Team]) -> tuple[list[Team], dict[tuple], dict[dict]]:
    """Given a list of teams (generally with the same record, though we are not checking
    here, since we don't really care), return list of teams ranked by the following stats
    tuple:

      (cohrt_win_pct, wl_factor, cohrt_pts_pct, tourn_pts_pct)

    where `wl_factor` (win-loss factor) is used to ensure that more wins is better (if all
    wins), more losses is worse (if all losses), and 0-0 sorts below 1-1, 2-2, etc.

    The other two return elements are the actual stats tuples and aggregated head-to-head
    game data for the cohort teams, both indexed by team seed.
    """
    stats = {}
    data = {}
    for tm in teams:
        wl_factor = 0
        # no need to exclude self from opps
        st = tm.get_game_stats(opps=teams)
        cohrt_games = st['games']
        if cohrt_games == 0:
            # REVISIT: should this be 0.0 instead???
            cohrt_win_pct = 0.5
            cohrt_pts_pct = 0.5
            data[tm.team_seed] = {
                'wins'       : 0,
                'losses'     : 0,
                'pts_for'    : 0,
                'pts_against': 0
            }
            # REVISIT: we currently sort this below other tied records!!!
            wl_factor = -1
        else:
            cohrt_tot_pts = st['team_pts'] + st['opp_pts']
            cohrt_win_pct = rnd_pct(st['wins'] / st['games'])
            cohrt_pts_pct = rnd_pct(st['team_pts'] / cohrt_tot_pts)
            data[tm.team_seed] = {
                'wins'       : st['wins'],
                'losses'     : cohrt_games - st['wins'],
                'pts_for'    : st['team_pts'],
                'pts_against': st['opp_pts']
            }
            # add weight (positive or negative) to all winning or all losing records,
            # based on number of cohort head-to-head games; otherwise treat all other
            # records as a pure percentage
            if st['wins'] == cohrt_games:
                wl_factor = cohrt_games
            elif st['wins'] == 0:
                wl_factor = -cohrt_games
        stats[tm.team_seed] = (cohrt_win_pct, wl_factor, cohrt_pts_pct, tm.tourn_pts_pct)

    # larger is better for all stats components
    sort_key = lambda tm: tuple(-x for x in stats[tm.team_seed])
    ranked = sorted(teams, key=sort_key)
    return ranked, stats, data

TeamGrps = list[set[Team]]
TeamWins = dict[Team, list[Team]]

def cyclic_win_groups(teams: list[Team]) -> tuple[TeamGrps, TeamWins]:
    """Identify/return cyclic win groups within the specified cohort (list of teams).
    Note that `team_wins` is also returned as a convenience for resuse by the caller.
    """
    seen: set[Team] = set()
    team_wins: TeamWins = {}  # map of teams with wins to losing opps
    cycle_grps: TeamGrps = []

    for tm in teams:
        # tm is included in opps, but will be ignored
        games: list[TeamGame] = tm.get_wins(opps=teams)
        if games:
            team_wins[tm] = [gm.opponent for gm in games]

    def check_for_cycle(team: Team, cycle_set: set[Team], cycle_seq: list[Team]) -> None:
        """Tree traversal of all sequences of winners, looking for cycles (repeated team
        in a branch); note that the cycle may not involve the team at the starting node.
        """
        nonlocal seen, team_wins, cycle_grps
        seen.add(team)
        cycle_set.add(team)
        cycle_seq.append(team)

        for opp in team_wins[team]:
            if opp in cycle_set:
                # cycle found
                assert opp in seen
                idx = cycle_seq.index(opp)
                grp = set(cycle_seq[idx:])
                if grp not in cycle_grps:
                    cycle_grps.append(grp)
            elif opp not in team_wins:
                # no cycle if opp has no wins
                pass
            else:
                # keep traversing
                check_for_cycle(opp, cycle_set.copy(), cycle_seq.copy())
        return

    for tm in team_wins:
        if tm not in seen:  # may have already been covered by prior starting node
            check_for_cycle(tm, set(), list())

    return cycle_grps, team_wins

Elevs = list[tuple[Team, Team]]  # tuple(winner, loser)

def elevate_winners(ranked: list[Team]) -> tuple[list[Team], Elevs, TeamGrps, TeamWins]:
    """Walk list of ranked teams from the bottom up, elevating head-to-head winners above
    their highest ranked losing opponent.  Elevation is skipped if the two teams are part
    of the same cyclic win group.  Note that (in the spirit of immutabile) a new list is
    created/returned even if no changes.

    We also return win_grps and team_wins (as passthroughs) since the caller may want the
    intermediary data/computation behind the reranking (e.g. for tie-breaking reports).
    """
    reranked = ranked.copy()
    win_grps, team_wins = cyclic_win_groups(reranked)

    elevs: Elevs = []
    grp_mates: bool = lambda x, y: sum({x, y} < grp for grp in win_grps) > 0
    for tm in reversed(ranked):  # NOTE: using unmutated input list here
        if tm not in team_wins:
            continue
        elev = None  # tuple(opp, opp_idx)
        for opp in team_wins[tm]:
            if not grp_mates(tm, opp):
                opp_idx = reranked.index(opp)
                if not elev or opp_idx < elev[1]:
                    elev = (opp, opp_idx)
        if not elev:
            continue
        tm_idx = reranked.index(tm)
        if elev[1] < tm_idx:
            popped = reranked.pop(tm_idx)
            assert popped == tm
            reranked.insert(elev[1], tm)
            elevs.append((tm, elev[0]))

    return reranked, elevs, win_grps, team_wins

MAX_TEAMS = 1000

def compute_tourn_ranks(teams: list[Team], finalize: bool = False) -> None:
    """This is similar to `compute_team_ranks`, except we use `rank_tourn_cohort` for
    tie-breaking and disregard division assignments and head-to-head play.  In addition,
    playoff results are factored in (when they are available), which we use to overwrite
    the provisional rankings from just after round robin play.

    TEMP: currently ignoring the `finalize` flag, but later should be used to ensure
    integrity for final overall tournament ranking!!!
    """
    tourn = TournInfo.get()
    tm_list = list(teams)  # make a shallow copy, since we will sort in-place

    rank_key = lambda x: (-(x.playoff_rank or MAX_TEAMS), x.tourn_win_pct)
    team_rank_data = [rank_key(tm) for tm in tm_list]
    tourn_ranks = rankdata(team_rank_data, method='min')

    for i, tm in enumerate(tm_list):
        tm.tourn_pos = tourn_ranks[i]

    # tournament ranking based on playoff_rank and then round robin win percentage, before
    # tie-breaking
    tm_list.sort(key=rank_key, reverse=True)
    for k, g in groupby(tm_list, key=rank_key):
        cohort = list(g)
        if len(cohort) == 1:
            tm = cohort[0]
            tm.tourn_rank = tm.tourn_pos
            tm.tourn_tb_crit = None
            tm.tourn_tb_data = None
            tm.save()
            continue
        cohort_pos = cohort[0].tourn_pos
        ranked, stats, data = rank_tourn_cohort(cohort)
        # REVISIT: we are not elevating head-to-head winners in determining overall
        # tournament rankings (for now), since it may not be possible to do this and
        # maintain fairness to cohort members across divisions (where tourn_pts_pct
        # matters)--but this will need some additional thinking!!!
        """
        ranked, elevs, win_grps, _ = elevate_winners(ranked)
        if elevs and DEBUG:
            for tm, opp in elevs:
                log.debug(f"Elevating {tm.team_seed} above {opp.team_seed} for tourn rank, "
                      f"pos {cohort_pos}")
        if win_grps and DEBUG:
            for grp in win_grps:
                grp_seeds = set(tm.team_seed for tm in grp)
                log.debug(f"Cyclic win group for tourn rank, pos {cohort_pos}, seeds {grp_seeds}")
        """
        for i, tm in enumerate(ranked):
            tm.tourn_rank = cohort_pos + i
            tm.tourn_tb_crit = stats[tm.team_seed]
            tm.tourn_tb_data = data[tm.team_seed]
            tm.save()

def compute_team_ranks(finalize: bool = False) -> None:
    """Note that we use `rankdata` to do the computation here, and `rank_team_cohort` to
    break ties.
    """
    tourn = TournInfo.get()
    div_iter = range(1, tourn.divisions + 1)
    tm_iter = Team.iter_teams()
    played = list(filter(lambda x: x.tourn_wins + x.tourn_losses, tm_iter))

    div_teams = {div: [] for div in div_iter}
    for i, tm in enumerate(played):
        div_teams[tm.div_num].append(tm)

    # FIX: overall tournament rankings piggyback off of us right now (for legacy reasons),
    # but we should disentangle and make callers decide what/which to invoke!!!  Note that
    # there are no playoff results yet, so only win and points percentage from round robin
    # play matters (for now).
    compute_tourn_ranks(played)

    for div, teams in div_teams.items():
        div_win_pcts = [tm.tourn_win_pct for tm in teams]
        div_ranks = rankdata(div_win_pcts, method='min')
        for i, tm in enumerate(teams):
            tm.div_pos = div_ranks[i]

        # division ranking based on win percentage, before tie-breaking
        teams.sort(key=lambda x: x.tourn_win_pct, reverse=True)
        for k, g in groupby(teams, key=lambda x: x.tourn_win_pct):
            cohort = list(g)
            if len(cohort) == 1:
                tm = cohort[0]
                tm.div_rank = tm.div_pos
                tm.div_tb_crit = None
                tm.div_tb_data = None
                tm.save()
                continue
            cohort_pos = cohort[0].div_pos
            ranked, stats, data = rank_team_cohort(cohort)
            ranked, elevs, win_grps, _ = elevate_winners(ranked)
            if elevs and DEBUG:
                for tm, opp in elevs:
                    log.debug(f"Elevating {tm.div_seed} above {opp.div_seed} for div {div} rank, "
                          f"pos {cohort_pos}")
            if win_grps and DEBUG:
                for grp in win_grps:
                    grp_seeds = set(tm.div_seed for tm in grp)
                    log.debug(f"Cyclic win group for div {div} rank, pos {cohort_pos}, "
                              f"seeds {grp_seeds}")
            for i, tm in enumerate(ranked):
                tm.div_rank = cohort_pos + i
                tm.div_tb_crit = stats[tm.team_seed]
                tm.div_tb_data = data[tm.team_seed]
                tm.save()

    if finalize:
        tourn.complete_stage(TournStage.TOURN_RANKS)

def build_playoff_bracket(bracket: Bracket) -> list[PlayoffGame]:
    """
    """
    tourn = TournInfo.get()
    nrounds = 3  # for all playoff matchups (where the third round might not be played)

    stage = None
    if bracket == Bracket.SEMIS:
        # NOTE: we were needlessly clever in generalizing the division assignment and
        # round robin bracket building above--we're not going to do that here!  Instead,
        # we are hard-coding exactly two divisions, where top rank in each division plays
        # second rank in the other, in a best 2-out-of-3 matchup.
        assert tourn.divisions == 2
        divisions = (1, 2)

        teams = list(Team.iter_playoff_teams(by_rank=True))
        # make sure best tourn_rank gets top billing here (matchup_num = 1)
        sign = 1 if teams[0].div_num == 1 else -1
        teams.sort(key=lambda x: (x.div_rank, sign * x.div_num))
        matchups = {
            1: (teams[0], teams[3]),
            2: (teams[1], teams[2])
        }
        stage = TournStage.SEMIS_BRACKET
    else:
        assert bracket == Bracket.FINALS
        # this now sorts by playoff_rank (based on TournInfo stage)
        teams = list(Team.iter_playoff_teams(by_rank=True))
        assert teams[0].playoff_match_wins == 1
        assert teams[1].playoff_match_wins == 1
        assert teams[2].playoff_match_wins == 0
        assert teams[3].playoff_match_wins == 0
        matchups = {
            1: (teams[0], teams[1])
        }
        stage = TournStage.FINALS_BRACKET

    games = []
    for matchup_num, (team1, team2) in matchups.items():
        for round_num in range(1, nrounds + 1):
            label = f'{bracket}-{matchup_num}-{round_num}'
            info = {'bracket'       : bracket,
                    'matchup_num'   : matchup_num,
                    'round_num'     : round_num,
                    'label'         : label,
                    'team1'         : team1,
                    'team2'         : team2,
                    'team1_name'    : team1.team_name,
                    'team2_name'    : team2.team_name,
                    'team1_div_rank': team1.div_rank,
                    'team2_div_rank': team2.div_rank}
            game = PlayoffGame.create(**info)
            games.append(game)

    assert stage is not None
    tourn.complete_stage(stage)
    return games

def validate_playoffs(bracket: Bracket, finalize: bool = False) -> None:
    """Note that we always validate all playoff stages/rounds.  There is more integrity
    check that can be done (e.g. ensure that semifinal winner are on the only ones with
    finals games, etc.), but it's probably not urgent (aggregious errors will be evident
    in the UI, since there are only four teams in play here--oh gee, I guess that's
    something else we could check as well...).
    """
    tm_list = list(Team.iter_playoff_teams())

    stats_tmpl = {
        'playoff_match_wins':   0,
        'playoff_match_losses': 0,
        'playoff_wins':         0,
        'playoff_losses':       0,
        'playoff_pts_for':      0,
        'playoff_pts_against':  0
    }
    tm_stats = {tm.id: stats_tmpl.copy() for tm in tm_list}

    unnec = []
    by_matchup = PlayoffGame.iter_games(by_matchup=True)
    for k, g in groupby(by_matchup, key=lambda x: (x.bracket, x.matchup_num)):
        # TODO: track stats for the matchup to tabulate/validate match wins/losses!!!
        matchup_stats1 = stats_tmpl.copy()
        matchup_stats2 = stats_tmpl.copy()
        for gm in g:
            if not gm.winner:
                assert not gm.team1_pts
                assert not gm.team2_pts
                unnec.append(gm)
                continue

            stats1 = tm_stats[gm.team1_id]
            stats2 = tm_stats[gm.team2_id]

            if gm.winner == gm.team1_name:
                stats1['playoff_wins'] += 1
                stats2['playoff_losses'] += 1
                matchup_stats1['playoff_wins'] += 1
                matchup_stats2['playoff_losses'] += 1
            else:
                stats1['playoff_losses'] += 1
                stats2['playoff_wins'] += 1
                matchup_stats1['playoff_losses'] += 1
                matchup_stats2['playoff_wins'] += 1

            stats1['playoff_pts_for'] += gm.team1_pts
            stats2['playoff_pts_for'] += gm.team2_pts
            stats1['playoff_pts_against'] += gm.team2_pts
            stats2['playoff_pts_against'] += gm.team1_pts
            matchup_stats1['playoff_pts_for'] += gm.team1_pts
            matchup_stats2['playoff_pts_for'] += gm.team2_pts
            matchup_stats1['playoff_pts_against'] += gm.team2_pts
            matchup_stats2['playoff_pts_against'] += gm.team1_pts

        # note that team1 and team2 (and hence stats1 and stats2) will be the same for all
        # games in this group (TODO: actually validate that here!!!), and we can continue
        # using the stats1/stats2 references from the last loop to do the matchup-level
        # stuff now
        if matchup_stats1['playoff_wins'] == 2:
            assert matchup_stats2['playoff_wins'] < 2
            stats1['playoff_match_wins'] += 1
            stats2['playoff_match_losses'] += 1
        elif matchup_stats2['playoff_wins'] == 2:
            assert matchup_stats1['playoff_wins'] < 2
            stats2['playoff_match_wins'] += 1
            stats1['playoff_match_losses'] += 1

    stats_tot = stats_tmpl.copy()
    for tm in tm_list:
        stats = tm_stats[tm.id]
        for k, v in stats.items():
            stats_tot[k] += v

        assert tm.playoff_match_wins   == stats['playoff_match_wins']
        assert tm.playoff_match_losses == stats['playoff_match_losses']
        assert tm.playoff_wins         == stats['playoff_wins']
        assert tm.playoff_losses       == stats['playoff_losses']
        assert tm.playoff_pts_for      == stats['playoff_pts_for']
        assert tm.playoff_pts_against  == stats['playoff_pts_against']

        ngames  = stats['playoff_wins'] + stats['playoff_losses']
        win_pct = rnd_pct(stats['playoff_wins'] / ngames)
        pts_tot = stats['playoff_pts_for'] + stats['playoff_pts_against']
        pts_pct = rnd_pct(stats['playoff_pts_for'] / pts_tot)

        # see note about floating points and rounding in `validate_seed_round` (above)
        assert tm.playoff_win_pct == win_pct
        assert tm.playoff_pts_pct == pts_pct

    assert stats_tot['playoff_match_wins'] == stats_tot['playoff_match_losses']
    assert stats_tot['playoff_wins']       == stats_tot['playoff_losses']
    assert stats_tot['playoff_pts_for']    == stats_tot['playoff_pts_against']

    for gm in unnec:
        assert gm.matchup_winner()

    if finalize:
        for gm in unnec:
            log.info(f"deleting unnecessary playoff game '{gm.label}'")
            gm.delete_instance()

        if bracket == Bracket.SEMIS:
            assert stats_tot['playoff_match_wins'] == 2
            TournInfo.mark_stage_complete(TournStage.SEMIS_TABULATE)
        else:
            assert bracket == Bracket.FINALS
            assert stats_tot['playoff_match_wins'] == 3
            TournInfo.mark_stage_complete(TournStage.FINALS_TABULATE)

def compute_playoff_ranks(bracket: Bracket, finalize: bool = False) -> None:
    """We don't have to get fancy here, since the rules are pretty simple: best 2-out-of-3
    matchups, and playoff win_pct followed by pts_pct to determine third and fourth place.
    """
    tourn = TournInfo.get()
    tm_list = list(Team.iter_teams())
    final_four = list(filter(lambda x: x.div_rank in [1, 2], tm_list))

    playoff_key = lambda x: (x.playoff_match_wins,
                             x.playoff_win_pct or 0.0,
                             x.playoff_pts_pct or 0.0)
    final_four.sort(key=playoff_key, reverse=True)
    for i, team in enumerate(final_four):
        team.playoff_rank = i + 1
        team.save()

    if bracket == Bracket.FINALS:
        compute_tourn_ranks(tm_list, finalize)

    if finalize:
        if bracket == Bracket.SEMIS:
            TournInfo.mark_stage_complete(TournStage.SEMIS_RANKS)
        else:
            assert bracket == Bracket.FINALS
            TournInfo.mark_stage_complete(TournStage.FINALS_RANKS)

########
# main #
########

import sys

from ckautils import parse_argv

# excludes utility and helper functions
MOD_FUNCS = [
    'tourn_create',
    'upload_roster',
    'generate_player_nums',
    'build_seed_bracket',
    'fake_seed_games',
    'validate_seed_round',
    'compute_player_ranks',
    'prepick_champ_partners',
    'fake_pick_partners',
    'build_tourn_teams',
    'compute_team_seeds',
    'build_tourn_bracket',
    'fake_tourn_games',
    'validate_tourn',
    'compute_team_ranks',
    'build_playoff_bracket',
    'validate_playoffs',
    'compute_playoff_ranks'
]

def main() -> int:
    """Built-in driver to invoke module functions

    Usage: python -m euchmgr <tourn_name> <func> [<args> ...]

    Functions/usage:
      - tourn_create [dates=<dates>] [venue=<venue>] [<schema_create kwargs>]
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
      - build_playoff_bracket
      - validate_playoffs
      - compute_playoff_ranks
    """
    if len(sys.argv) < 2:
        print(main.__doc__)
        print(f"Tournament name not specified", file=sys.stderr)
        return -1
    if len(sys.argv) < 3:
        print(main.__doc__)
        print(f"Module function not specified", file=sys.stderr)
        return -1
    elif sys.argv[2] not in MOD_FUNCS:
        print(f"Unknown module function '{sys.argv[2]}'", file=sys.stderr)
        return -1

    tourn_name = sys.argv[1]
    mod_func = globals()[sys.argv[2]]
    args, kwargs = parse_argv(sys.argv[3:])

    db_init(tourn_name, force=True)
    mod_func(*args, **kwargs)  # will throw exceptions on error
    db_close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
