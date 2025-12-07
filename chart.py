#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Blueprint for chart rendering
"""

from flask import Blueprint, render_template, abort

from database import db_init
from schema import (GAME_PTS, TournInfo, Player, SeedGame, Team, TournGame, PlayerGame,
                    TeamGame)
from euchmgr import get_div_teams

#################
# utility stuff #
#################

Numeric = int | float
FLOAT_PREC = 1

def round_val(val: Numeric) -> Numeric:
    """Provide the appropriate level of rounding for the leaderboard or stat value (does
    not change the number type); passthrough for non-numeric types (e.g. bool or str)
    """
    if isinstance(val, float):
        return round(val, FLOAT_PREC)
    return val

def fmt_score(pts: int) -> str:
    """Version for scoring charts--markup score if game-winning (bold)
    """
    # special case for byes (no markup)
    if pts == -1:
        return '-'

    ret = str(pts)
    if pts >= GAME_PTS:
        ret = f"<b>{ret}</b>"

    return ret

def fmt_stat(val: Numeric) -> str:
    """Version for scoring charts--handle empty values properly.  Note that float vals are
    assumed to represent percentages.
    """
    if val is None:
        return ''
    elif isinstance(val, float):
        return f"{round_val(val)}%"
    else:
        assert isinstance(val, int)
        return str(val)

def fmt_tally(pts: int) -> str:
    """Print arguments for <img> tag for showing point tallies
    """
    if pts == 0:
        return ''
    tally_file = f"/static/tally_{pts}.png"
    return f'src="{tally_file}" height="15" width="50"'

###################
# blueprint stuff #
###################

chart = Blueprint('chart', __name__)
CHART_TEMPLATE = "chart.html"

SD_BRACKET  = "Seeding Round Bracket"
SD_SCORES   = "Seeding Round Scores"
RR_BRACKETS = "Round Robin Brackets"
RR_SCORES   = "Round Robin Scores"

CHART_FUNCS = [
    'sd_bracket',
    'sd_scores',
    'rr_brackets',
    'rr_scores'
]

@chart.get("/<path:chart_path>")
def get_chart(chart_path: str) -> str:
    """Render specified chart
    """
    chart, tourn_name = chart_path.split('/', 1)
    if chart not in CHART_FUNCS:
        abort(404, f"Invalid chart func '{chart}'")

    db_init(tourn_name)
    tourn = TournInfo.get(requery=True)
    return globals()[chart](tourn)

def render_chart(context: dict) -> str:
    """Common post-processing of context before rendering chart pages through Jinja
    """
    return render_template(CHART_TEMPLATE, **context)

##############
# sd_bracket #
##############

def sd_bracket(tourn: TournInfo) -> str:
    """Render seed round bracket as a chart
    """
    rnd_tables = tourn.players // 4
    rnd_byes = tourn.players % 4

    matchups = {}  # key sequence: rnd, tbl -> matchup_html
    sg_iter = SeedGame.iter_games(include_byes=True)
    for sg in sg_iter:
        rnd = sg.round_num
        tbl = sg.table_num
        if rnd not in matchups:
            matchups[rnd] = {}
        assert tbl not in matchups[rnd]
        if tbl:
            matchups[rnd][tbl] = "<br>vs.<br>".join(sg.team_tags)
        else:
            matchups[rnd][tbl] = "<br>".join(sg.bye_tags)  # bye(s)

    assert len(matchups) == tourn.seed_rounds
    for rnd, tbls in matchups.items():
        assert len(tbls) == rnd_tables + int(bool(rnd_byes))

    context = {
        'chart_num' : 0,
        'title'     : SD_BRACKET,
        'tourn'     : tourn,
        'rnds'      : tourn.seed_rounds,
        'rnd_tables': rnd_tables,
        'rnd_byes'  : rnd_byes,
        'matchups'  : matchups,
        'bold_color': '#555555'
    }
    return render_chart(context)

#############
# sd_scores #
#############

def sd_scores(tourn: TournInfo) -> str:
    """Render seed round scores as a chart
    """
    pl_list = sorted(Player.iter_players(), key=lambda pl: pl.player_num)
    # sub-dict key is rnd, value is pts
    team_pts = {pl.player_num: {} for pl in pl_list}
    opp_pts  = {pl.player_num: {} for pl in pl_list}
    wins     = {pl.player_num: 0 for pl in pl_list}
    losses   = {pl.player_num: 0 for pl in pl_list}

    pg_list = list(PlayerGame.iter_games(include_byes=True))
    not_bye = lambda g: not g.is_bye
    max_rnd = lambda ls: max(g.round_num for g in ls) if ls else 0
    cur_rnd = max_rnd(list(filter(not_bye, pg_list)))
    for pg in pg_list:
        pl_num = pg.player_num
        rnd = pg.round_num
        assert rnd not in team_pts[pl_num]
        assert rnd not in opp_pts[pl_num]
        if not pg.is_bye:
            team_pts[pl_num][rnd] = fmt_score(pg.team_pts)
            opp_pts[pl_num][rnd] = fmt_score(pg.opp_pts)
            if pg.is_winner:
                wins[pl_num] += 1
            else:
                losses[pl_num] += 1
        elif rnd <= cur_rnd:
            team_pts[pl_num][rnd] = fmt_score(-1)
            opp_pts[pl_num][rnd] = fmt_score(-1)

    win_tallies = {}
    loss_tallies = {}
    for pl in pl_list:
        win_tallies[pl.player_num] = fmt_tally(wins[pl.player_num])
        loss_tallies[pl.player_num] = fmt_tally(losses[pl.player_num])

    context = {
        'chart_num'   : 1,
        'title'       : SD_SCORES,
        'tourn'       : tourn,
        'rnds'        : tourn.seed_rounds,
        'players'     : pl_list,
        'team_pts'    : team_pts,
        'opp_pts'     : opp_pts,
        'wins'        : wins,
        'losses'      : losses,
        'win_tallies' : win_tallies,
        'loss_tallies': loss_tallies,
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

##############
# rr_bracket #
##############

def rr_brackets(tourn: TournInfo) -> str:
    """Render round robin brackets as a chart
    """
    div_list   = list(range(1, tourn.divisions + 1))
    div_teams  = get_div_teams(tourn, requery=True)
    max_teams  = max(div_teams)
    div_tables = {}
    div_byes   = {}
    for i, div in enumerate(div_list):
        div_tables[div] = div_teams[i] // 2
        div_byes[div] = div_teams[i] % 2

    # key sequence for sub-dict: rnd, tbl -> matchup_html
    matchups = {div: {} for div in div_list}
    tg_iter = TournGame.iter_games(include_byes=True)
    for tg in tg_iter:
        div = tg.div_num
        rnd = tg.round_num
        tbl = tg.table_num
        if rnd not in matchups[div]:
            matchups[div][rnd] = {}
        assert tbl not in matchups[div][rnd]
        if tbl:
            matchups[div][rnd][tbl] = "<br>vs.<br>".join(tg.team_tags)
        else:
            matchups[div][rnd][tbl] = tg.bye_tag

    for div in div_list:
        assert len(matchups[div]) == tourn.tourn_rounds
        for rnd, tbls in matchups[div].items():
            assert len(tbls) == div_tables[div] + div_byes[div]

    context = {
        'chart_num' : 2,
        'title'     : RR_BRACKETS,
        'tourn'     : tourn,
        'rnds'      : tourn.tourn_rounds,
        'div_list'  : div_list,
        'div_tables': div_tables,
        'div_byes'  : div_byes,
        'matchups'  : matchups,
        'bold_color': '#555555'
    }
    return render_chart(context)

#############
# rr_scores #
#############

def rr_scores(tourn: TournInfo) -> str:
    """Render round robin scores as a chart
    """
    div_list = list(range(1, tourn.divisions + 1))
    tm_list  = sorted(Team.iter_teams(), key=lambda tm: tm.team_seed)
    # inner dict represents points by round {rnd: pts}
    team_pts = {tm.team_seed: {} for tm in tm_list}
    opp_pts  = {tm.team_seed: {} for tm in tm_list}
    wins     = {tm.team_seed: 0 for tm in tm_list}
    losses   = {tm.team_seed: 0 for tm in tm_list}

    tg_list = list(TeamGame.iter_games(include_byes=True))
    not_bye = lambda g: not g.is_bye
    max_rnd = lambda ls: max(g.round_num for g in ls) if ls else 0
    cur_rnd = {div: max_rnd(list(filter(not_bye, tg_list))) for div in div_list}
    for tg in tg_list:
        div = tg.team.div_num
        tm_seed = tg.team_seed
        assert tm_seed == tg.team.team_seed
        rnd = tg.round_num
        assert rnd not in team_pts[tm_seed]
        assert rnd not in opp_pts[tm_seed]
        if not tg.is_bye:
            team_pts[tm_seed][rnd] = fmt_score(tg.team_pts)
            opp_pts[tm_seed][rnd] = fmt_score(tg.opp_pts)
            if tg.is_winner:
                wins[tm_seed] += 1
            else:
                losses[tm_seed] += 1
        elif rnd <= cur_rnd[div]:
            team_pts[tm_seed][rnd] = fmt_score(-1)
            opp_pts[tm_seed][rnd] = fmt_score(-1)

    div_teams = {div: [] for div in div_list}
    # the following are all keyed off of team_seed
    win_tallies = {}
    loss_tallies = {}
    for tm in tm_list:
        div = tm.div_num
        tm_seed = tm.team_seed

        div_teams[div].append(tm)
        win_tallies[tm_seed] = fmt_tally(wins[tm_seed])
        loss_tallies[tm_seed] = fmt_tally(losses[tm_seed])

    context = {
        'chart_num'   : 3,
        'title'       : RR_SCORES,
        'tourn'       : tourn,
        'rnds'        : tourn.tourn_rounds,
        'div_list'    : div_list,
        'div_teams'   : div_teams,
        'team_pts'    : team_pts,
        'opp_pts'     : opp_pts,
        'wins'        : wins,
        'losses'      : losses,
        'win_tallies' : win_tallies,
        'loss_tallies': loss_tallies,
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)
