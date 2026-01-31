# -*- coding: utf-8 -*-

"""Blueprint for chart rendering
"""

from flask import Blueprint, session, render_template, abort

from schema import (GAME_PTS, PTS_PCT_NA, TournInfo, Player, SeedGame, Team, TournGame,
                    PlayerGame, TeamGame)
from euchmgr import get_div_teams

#################
# utility stuff #
#################

Numeric = int | float
PCT_PREC = 3
PCT_FMT = '.03f'

def fmt_pct(val: float) -> str:
    """Provide consistent formatting for percentage values (appropriate rounding and
    look), used for charts, dashboards, and reports.
    """
    if val is None:
        return ''
    elif val == PTS_PCT_NA:
        return '&ndash;'  # or "n/a"?
    # take care of (possible!) exceptions first--yes, the code below may produce the same
    # string, but we want to allow ourselves the freedom to make this something different
    if val == 1.0:
        return '1.000'

    # make everything else look like .xxx (with trailing zeros)
    as_str = f"{round(val, PCT_PREC):{PCT_FMT}}"
    if as_str.startswith('0.'):
        return as_str[1:]
    # not expecting negative input or anything >1.0
    assert False, f"unexpected percentage value of '{val}'"

def fmt_score(pts: int) -> str:
    """Version for scoring charts--markup score if game-winning (bold)
    """
    # special case for byes (no markup)
    if pts == -1:
        return '&ndash;'

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
        return f"{fmt_pct(val)}"
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

# quick and dirty stuff (yucky!)
SPC = lambda x: '&nbsp;' * x
PTS = lambda x: f"{SPC(1)}{x}{SPC(2)}" if x == GAME_PTS else f"{SPC(2)}{x}{SPC(2)}"

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

@chart.get("/<chart>")
def get_chart(chart: str) -> str:
    """Render specified chart
    """
    if chart not in CHART_FUNCS:
        abort(404, f"Invalid chart '{chart}'")

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
    labels   = {}
    complete = {}
    sg_iter = SeedGame.iter_games(include_byes=True)
    for sg in sg_iter:
        rnd = sg.round_num
        tbl = sg.table_num
        if rnd not in matchups:
            matchups[rnd] = {}
            labels[rnd]   = {}
            complete[rnd] = {}
        assert tbl not in matchups[rnd]
        assert tbl not in labels[rnd]
        assert tbl not in complete[rnd]
        labels[rnd][tbl] = sg.label
        complete[rnd][tbl] = False
        if tbl:
            if sg.winner:
                tm1_str = f"{sg.team_tags[0]}{SPC(3)}<u class='u2'>{PTS(sg.team1_pts)}</u>"
                tm2_str = f"{sg.team_tags[1]}{SPC(3)}<u class='u2'>{PTS(sg.team2_pts)}</u>"
                complete[rnd][tbl] = True
            else:
                tm1_str = f"{sg.team_tags[0]}{SPC(3)}<u class='u2'>{SPC(5)}</u>"
                tm2_str = f"{sg.team_tags[1]}{SPC(3)}<u class='u2'>{SPC(5)}</u>"
            matchups[rnd][tbl] = f"{tm1_str}<br>vs.<br>{tm2_str}"
        else:
            matchups[rnd][tbl] = "<br>".join(sg.bye_tags)  # one or more byes

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
        'labels'    : labels,
        'complete'  : complete,
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
    labels   = {div: {} for div in div_list}
    complete = {div: {} for div in div_list}
    tg_iter = TournGame.iter_games(include_byes=True)
    for tg in tg_iter:
        div = tg.div_num
        rnd = tg.round_num
        tbl = tg.table_num
        if rnd not in matchups[div]:
            matchups[div][rnd] = {}
            labels[div][rnd]   = {}
            complete[div][rnd] = {}
        assert tbl not in matchups[div][rnd]
        assert tbl not in labels[div][rnd]
        assert tbl not in complete[div][rnd]
        labels[div][rnd][tbl] = tg.label
        complete[div][rnd][tbl] = False
        if tbl:
            if tg.winner:
                tm1_str = f"{tg.team_tags[0]}{SPC(3)}<u class='u2'>{PTS(tg.team1_pts)}</u>"
                tm2_str = f"{tg.team_tags[1]}{SPC(3)}<u class='u2'>{PTS(tg.team2_pts)}</u>"
                complete[div][rnd][tbl] = True
            else:
                tm1_str = f"{tg.team_tags[0]}{SPC(3)}<u class='u2'>{SPC(5)}</u>"
                tm2_str = f"{tg.team_tags[1]}{SPC(3)}<u class='u2'>{SPC(5)}</u>"
            matchups[div][rnd][tbl] = f"{tm1_str}<br>vs.<br>{tm2_str}"
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
        'labels'    : labels,
        'complete'  : complete,
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
    team_pts = {tm.id: {} for tm in tm_list}
    opp_pts  = {tm.id: {} for tm in tm_list}
    wins     = {tm.id: 0 for tm in tm_list}
    losses   = {tm.id: 0 for tm in tm_list}

    tg_list = list(TeamGame.iter_games(include_byes=True))
    not_bye = lambda g: not g.is_bye
    max_rnd = lambda ls: max(g.round_num for g in ls) if ls else 0
    cur_rnd = {div: max_rnd(list(filter(not_bye, tg_list))) for div in div_list}
    for tg in tg_list:
        div = tg.team.div_num
        tm_id = tg.team_id
        assert tm_id == tg.team.id
        rnd = tg.round_num
        assert rnd not in team_pts[tm_id]
        assert rnd not in opp_pts[tm_id]
        if not tg.is_bye:
            team_pts[tm_id][rnd] = fmt_score(tg.team_pts)
            opp_pts[tm_id][rnd] = fmt_score(tg.opp_pts)
            if tg.is_winner:
                wins[tm_id] += 1
            else:
                losses[tm_id] += 1
        elif rnd <= cur_rnd[div]:
            team_pts[tm_id][rnd] = fmt_score(-1)
            opp_pts[tm_id][rnd] = fmt_score(-1)

    div_teams = {div: [] for div in div_list}
    # the following are all keyed off of team id
    win_tallies = {}
    loss_tallies = {}
    for tm in tm_list:
        div = tm.div_num
        tm_id = tm.id

        div_teams[div].append(tm)
        win_tallies[tm_id] = fmt_tally(wins[tm_id])
        loss_tallies[tm_id] = fmt_tally(losses[tm_id])

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
