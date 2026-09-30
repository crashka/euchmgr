# -*- coding: utf-8 -*-

"""Blueprint for chart rendering
"""

from ckautils import typecast
from flask import Blueprint, session, request, render_template, abort

from security import current_user
from schema import GAME_PTS, RankType, RankAction
from ui_schema import (Numeric, fmt_pct, fmt_tally, TournInfo, Player, SeedGame, Team,
                       TournGame, PlayerGame, TeamGame)
from ui_common import referrer_path
from euchmgr import get_div_maps

#################
# utility stuff #
#################

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

def fmt_stat(val: Numeric | str) -> str:
    """Version for scoring charts--handle empty values properly.  Note that float vals are
    assumed to represent percentages.
    """
    if val is None:
        return ''
    elif isinstance(val, float):
        return f"{fmt_pct(val)}"
    elif isinstance(val, int):
        return str(val)
    else:
        assert isinstance(val, str)
        return val

# quick and dirty stuff (yucky!)
SPC = lambda x: '&nbsp;' * x
PTS = lambda x: f"{SPC(1)}{x}{SPC(2)}" if x == GAME_PTS else f"{SPC(2)}{x}{SPC(2)}"

###################
# blueprint stuff #
###################

chart = Blueprint('chart', __name__)
CHART_TEMPLATE = "chart.html"

SD_BRACKET   = "Seeding Round Bracket"
SD_SCORES    = "Seeding Round Scores"
RR_BRACKETS  = "Round Robin Brackets"
RR_SCORES    = "Round Robin Scores"
TRN_RESULTS  = "Team Rank Results (pre-playoff)"
FNL_RESULTS  = "Final Tournament Results"
FNL_RANK_ADJ = "Final Tournament Rank Adjustment"
DIV_RESULTS  = "Division {0} Results"
DIV_RANK_ADJ = "Division {0} Rank Adjustment"
SD_RESULTS   = "Seeding Round Results"
SD_RANK_ADJ  = "Seeding Round Rank Adjustment"

CHART_FUNCS = [
    'sd_bracket',
    'sd_scores',
    'rr_brackets',
    'rr_scores',
    'trn_results',
    'fnl_results',
    'fnl_rank_adj',
    'div_results',
    'div_rank_adj',
    'sd_results',
    'sd_rank_adj'
]

@chart.get("/<chart>")
def get_chart(chart: str) -> str:
    """Render specified chart
    """
    if chart not in CHART_FUNCS:
        abort(404, f"Invalid chart '{chart}'")

    tourn = TournInfo.get(requery=True)
    return globals()[chart](tourn)

@chart.get("/<chart>/<target>")
def get_chart_targ(chart: str, target: str) -> str:
    """Render specified chart (with target)
    """
    if chart not in CHART_FUNCS:
        abort(404, f"Invalid chart '{chart}'")

    tourn = TournInfo.get(requery=True)
    return globals()[chart](typecast(target), tourn)

def render_chart(context: dict) -> str:
    """Common post-processing of context before rendering chart pages through Jinja
    """
    return render_template(CHART_TEMPLATE, **context)

#######################
# rank hist/adj stuff #
#######################

RANK_HIST_REPORT = {
    RankType.SEED : '/report/seed_rank_hist',
    RankType.DIV  : '/report/div_rank_hist',
    RankType.FINAL: '/report/final_rank_hist',
    RankType.TOURN: '/report/tourn_rank_hist'
}

RANK_ADJ_ACTION = {
    RankType.SEED : '/players/rank_adj/seed',
    RankType.DIV  : '/teams/rank_adj/div',
    RankType.FINAL: '/teams/rank_adj/final'
}

##############
# sd_bracket #
##############

def sd_bracket(tourn: TournInfo) -> str:
    """Render seed round bracket as a chart.
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
    """Render seed round scores as a chart.  Note that this chart ignores ranking
    adjustments (if any), since it is intended to reflect the active-play results and
    naive computations.
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
    """Render round robin brackets as a chart.
    """
    div_list   = list(range(1, tourn.divisions + 1))
    div_maps   = get_div_maps(tourn)
    div_tables = {}
    div_byes   = {}
    for div in div_list:
        assert div in div_maps
        nteams = len(div_maps[div])
        div_tables[div] = nteams // 2
        div_byes[div] = nteams % 2

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
    """Render round robin scores as a chart.  Note that this chart ignores ranking
    adjustments (if any), since it is intended to reflect the active-play results and
    naive computations
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

###############
# trn_results #
###############

def trn_results(tourn: TournInfo) -> str:
    """Render intermediary/pre-playoff tournament results as a chart
    """
    rank_type = RankType.TOURN
    #tm_list  = sorted(Team.iter_teams(), key=lambda tm: tm.tourn_rank_eff)
    tm_iter  = Team.iter_teams(div=None, by_rank=True)
    tm_list = list(filter(lambda x: x.tourn_wins + x.tourn_losses, tm_iter))

    tb_crit = {}
    rank_note = {}
    for tm in tm_list:
        tb_crit[tm.id] = f"Tie-break criteria: {tm.tourn_tb_crit}"
        note = f"Computed rank: {tm.tourn_rank}"
        if tm.tourn_rank_adj:
            note += chr(10) + f"Adjusted to: {tm.tourn_rank_adj}"
        rank_note[tm.id] = note

    context = {
        'chart_num'   : 4,
        'title'       : TRN_RESULTS,
        'user'        : current_user,
        'tourn'       : tourn,
        'teams'       : tm_list,
        'tb_crit'     : tb_crit,
        'rank_note'   : rank_note,
        'hist_rpt'    : RANK_HIST_REPORT[rank_type],
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

###############
# fnl_results #
###############

def fnl_results(tourn: TournInfo) -> str:
    """Render final tournament results as a chart
    """
    rank_type = RankType.FINAL
    #tm_list = sorted(Team.iter_teams(), key=lambda tm: tm.final_rank_eff)
    tm_iter  = Team.iter_teams(div=0, by_rank=True)
    tm_list = list(filter(lambda x: x.tourn_wins + x.tourn_losses, tm_iter))

    tb_crit = {}
    rank_note = {}
    for tm in tm_list:
        tb_crit[tm.id] = f"Tie-break criteria: {tm.final_tb_crit}"
        note = f"Computed rank: {tm.final_rank}"
        if tm.final_rank_adj:
            note += chr(10) + f"Adjusted to: {tm.final_rank_adj}"
        rank_note[tm.id] = note

    context = {
        'chart_num'   : 5,
        'title'       : FNL_RESULTS,
        'user'        : current_user,
        'tourn'       : tourn,
        'teams'       : tm_list,
        'tb_crit'     : tb_crit,
        'rank_note'   : rank_note,
        'hist_rpt'    : RANK_HIST_REPORT[rank_type],
        'adjust_url'  : '/chart/fnl_rank_adj',
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

################
# fnl_rank_adj #
################

def fnl_rank_adj(tourn: TournInfo) -> str:
    """Render final tournament rank_adjustment as a chart
    """
    rank_type = RankType.FINAL
    tm_list = sorted(Team.iter_teams(), key=lambda tm: tm.final_rank_eff)
    parent_url = referrer_path(request)

    tb_crit = {}
    rank_note = {}
    for tm in tm_list:
        tb_crit[tm.id] = f"Tie-break criteria: {tm.final_tb_crit}"
        note = f"Computed rank: {tm.final_rank}"
        if tm.final_rank_adj:
            note += chr(10) + f"Previously adjusted to: {tm.final_rank_adj}"
        rank_note[tm.id] = note

    context = {
        'chart_num'   : 6,
        'title'       : FNL_RANK_ADJ,
        'user'        : current_user,
        'tourn'       : tourn,
        'nteams'      : len(tm_list),
        'teams'       : tm_list,
        'tb_crit'     : tb_crit,
        'rank_note'   : rank_note,
        'action'      : RANK_ADJ_ACTION[rank_type],
        'cancel_url'  : parent_url,
        'redirect_to' : parent_url,
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

###############
# div_results #
###############

DIV_DFLT = 1

def div_results(tourn: TournInfo) -> str:
    """Render tournament round robin results as a chart (for the specified division)
    """
    rank_type = RankType.DIV
    div_num = typecast(request.args.get('div')) or DIV_DFLT
    assert div_num in (1, 2)
    other_div = None if tourn.playoff_teams == 2 else (div_num % 2 + 1)
    #tm_list = sorted(Team.iter_teams(div=div_num), key=lambda tm: tm.div_rank_eff)
    tm_iter  = Team.iter_teams(div=div_num, by_rank=True)
    tm_list = list(filter(lambda x: x.tourn_wins + x.tourn_losses, tm_iter))

    tb_crit = {}
    rank_note = {}
    for tm in tm_list:
        tb_crit[tm.id] = f"Tie-break criteria: {tm.div_tb_crit}"
        note = f"Computed rank: {tm.div_rank}"
        if tm.div_rank_adj:
            note += chr(10) + f"Adjusted to: {tm.div_rank_adj}"
        rank_note[tm.id] = note

    RESULTS_URL  = '/chart/div_results?div={0}'
    RANK_ADJ_URL = '/chart/div_rank_adj?div={0}'
    context = {
        'chart_num'   : 7,
        'title'       : DIV_RESULTS.format(div_num),
        'title_note'  : "&nbsp;<i>(click to switch divisions)</i>" if other_div else None,
        'user'        : current_user,
        'tourn'       : tourn,
        'div_num'     : div_num,
        'teams'       : tm_list,
        'tb_crit'     : tb_crit,
        'rank_note'   : rank_note,
        'other_div'   : other_div,
        'switch_divs' : RESULTS_URL.format(other_div),
        'hist_rpt'    : RANK_HIST_REPORT[rank_type],
        'adjust_url'  : RANK_ADJ_URL.format(div_num),
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

################
# div_rank_adj #
################

def div_rank_adj(tourn: TournInfo) -> str:
    """Render tournament round robin rank adjustment as a chart (for the specified
    division)
    """
    rank_type = RankType.DIV
    div_num = typecast(request.args.get('div')) or DIV_DFLT
    assert div_num in (1, 2)
    tm_list = sorted(Team.iter_teams(div=div_num), key=lambda tm: tm.div_rank_eff)
    parent_url = referrer_path(request)

    tb_crit = {}
    rank_note = {}
    for tm in tm_list:
        tb_crit[tm.id] = f"Tie-break criteria: {tm.div_tb_crit}"
        note = f"Computed rank: {tm.div_rank}"
        if tm.div_rank_adj:
            note += chr(10) + f"Previously adjusted to: {tm.div_rank_adj}"
        rank_note[tm.id] = note

    context = {
        'chart_num'   : 8,
        'title'       : DIV_RANK_ADJ.format(div_num),
        'user'        : current_user,
        'tourn'       : tourn,
        'div_num'     : div_num,
        'nteams'      : len(tm_list),
        'teams'       : tm_list,
        'tb_crit'     : tb_crit,
        'rank_note'   : rank_note,
        'action'      : RANK_ADJ_ACTION[rank_type],
        'cancel_url'  : parent_url,
        'redirect_to' : parent_url,
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

##############
# sd_results #
##############

def sd_results(tourn: TournInfo) -> str:
    """Render seeding round results as a chart
    """
    rank_type = RankType.SEED
    #pl_list = sorted(Player.iter_players(), key=lambda pl: pl.player_rank_eff)
    pl_iter  = Player.iter_players(by_rank=True)
    pl_list = list(filter(lambda x: x.seed_wins + x.seed_losses, pl_iter))

    tb_crit = {}
    rank_note = {}
    for pl in pl_list:
        tb_crit[pl.id] = f"Tie-break criteria: {pl.seed_tb_crit}"
        note = f"Computed rank: {pl.player_rank}"
        if pl.player_rank_adj:
            note += chr(10) + f"Adjusted to: {pl.player_rank_adj}"
        rank_note[pl.id] = note

    context = {
        'chart_num'   : 9,
        'title'       : SD_RESULTS,
        'user'        : current_user,
        'tourn'       : tourn,
        'players'     : pl_list,
        'tb_crit'     : tb_crit,
        'rank_note'   : rank_note,
        'hist_rpt'    : RANK_HIST_REPORT[rank_type],
        'adjust_url'  : '/chart/sd_rank_adj',
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

###############
# sd_rank_adj #
###############

def sd_rank_adj(tourn: TournInfo) -> str:
    """Render seeding round rank adjustment as a chart
    """
    rank_type = RankType.SEED
    pl_list = sorted(Player.iter_players(), key=lambda pl: pl.player_rank_eff)
    parent_url = referrer_path(request)

    tb_crit = {}
    rank_note = {}
    for pl in pl_list:
        tb_crit[pl.id] = f"Tie-break criteria: {pl.seed_tb_crit}"
        note = f"Computed rank: {pl.player_rank}"
        if pl.player_rank_adj:
            note += chr(10) + f"Previously adjusted to: {pl.player_rank_adj}"
        rank_note[pl.id] = note

    context = {
        'chart_num'   : 10,
        'title'       : SD_RANK_ADJ,
        'user'        : current_user,
        'tourn'       : tourn,
        'nplayers'    : len(pl_list),
        'players'     : pl_list,
        'tb_crit'     : tb_crit,
        'rank_note'   : rank_note,
        'action'      : RANK_ADJ_ACTION[rank_type],
        'cancel_url'  : parent_url,
        'redirect_to' : parent_url,
        'fmt_stat'    : fmt_stat,
        'bold_color'  : '#555555'
    }
    return render_chart(context)
