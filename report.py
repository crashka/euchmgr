# -*- coding: utf-8 -*-

"""Blueprint for report rendering
"""
from itertools import groupby

from flask import Blueprint, session, render_template, abort

from schema import GAME_PTS, TournInfo, Player, PlayerGame, Team, TeamGame
from euchmgr import Elevs, TeamGrps, rank_team_cohort, elevate_winners
from chart import Numeric, round_val, fmt_tally

#################
# utility stuff #
#################


###################
# blueprint stuff #
###################

report = Blueprint('report', __name__)
REPORT_TEMPLATE = "report.html"

SD_TB_REPORT = "Seeding Round Tie-Breaker Report"
RR_TB_REPORT = "Round Robin Tie-Breaker Report"

REPORT_FUNCS = [
    'sd_tb_report',
    'rr_tb_report'
]

@report.get("/<report>")
def get_report(report: str) -> str:
    """Render specified report
    """
    if report not in REPORT_FUNCS:
        abort(404, f"Invalid report func '{report}'")

    tourn = TournInfo.get(requery=True)
    return globals()[report](tourn)

def render_report(context: dict) -> str:
    """Common post-processing of context before rendering report pages through Jinja
    """
    return render_template(REPORT_TEMPLATE, **context)

################
# sd_tb_report #
################

# HORRIBLY HACKY: this same format func is hacked into schema.py a few places (as well as
# in fmt_team_name [euchmgr.py])--we really need to refactor/consolidate all of this!!!
player_tag = lambda x: f"{x.nick_name} ({x.player_num})"

def sd_tb_report(tourn: TournInfo) -> str:
    """Render seeding round tie-breaker report
    """
    pl_list = Player.get_player_map().values()
    by_rank = sorted(pl_list, key=lambda x: x.player_rank)

    # dict keys: cohort_pos (int), team (Team)
    pos_rpt: dict[int, dict[Team, list[SeedGame]]] = {}
    pos_info: dict[int, str] = {}
    pos_cohort: dict[int, list[str]] = {}
    for k, g in groupby(by_rank, key=lambda x: x.player_pos):
        cohort = list(g)
        if len(cohort) == 1:
            continue
        cohort_pos = cohort[0].player_pos
        cohort_win_pct = cohort[0].seed_win_pct
        cohort_rpt = {}
        plyr_list = []
        pos_rpt[cohort_pos] = cohort_rpt
        pos_info[cohort_pos] = f"Win Pct: {round(cohort_win_pct, 2)}%"
        pos_cohort[cohort_pos] = plyr_list
        for pl in cohort:
            games = pl.get_opps_games(cohort)  # list[SeedGame]
            cohort_rpt[pl] = games
            plyr_list.append(player_tag(pl))

    context = {
        'report_num' : 0,
        'title'      : SD_TB_REPORT,
        'tourn'      : tourn,
        'len'        : len,
        'round'      : round,
        'pos_rpt'    : pos_rpt,
        'pos_info'   : pos_info,
        'pos_cohort' : pos_cohort,
        'report_by'  : 'team'
    }
    return render_report(context)

################
# rr_tb_report #
################

# HORRIBLY HACKY: same as above (for sd_tb_report)!!!
team_tag = lambda x: f"{x.team_name} ({x.div_seed})"

def rr_tb_report(tourn: TournInfo) -> str:
    """Render round robin tie-breaker report
    """
    div_iter = range(1, tourn.divisions + 1)
    tm_list = Team.get_team_map().values()
    by_rank = sorted(tm_list, key=lambda x: x.div_rank)

    # dict keys: div (int), cohort_pos (int), team (Team)
    div_rpt: dict[int, dict[int, dict[Team, list[SeedGame]]]] = {}
    div_info: dict[int, dict[int, str]] = {}
    div_cohort: dict[int, dict[int, list[str]]] = {}
    div_elevs: dict[int, dict[int, Elevs]] = {}
    div_win_grps: dict[int, dict[int, TeamGrps]] = {}
    div_idents: dict[int, dict[int, list[Team]]] = {}
    for div in div_iter:
        pos_rpt = {}
        pos_info = {}
        pos_cohort = {}
        pos_elevs = {}
        pos_win_grps = {}
        pos_idents = {}
        div_rpt[div] = pos_rpt
        div_info[div] = pos_info
        div_cohort[div] = pos_cohort
        div_elevs[div] = pos_elevs
        div_win_grps[div] = pos_win_grps
        div_idents[div] = pos_idents

        div_teams = list(filter(lambda x: x.div_num == div, by_rank))
        for k, g in groupby(div_teams, key=lambda x: x.div_pos):
            cohort = list(g)
            if len(cohort) == 1:
                continue
            cohort_pos = cohort[0].div_pos
            cohort_win_pct = cohort[0].tourn_win_pct
            cohort_rpt = {}
            team_list = []
            pos_rpt[cohort_pos] = cohort_rpt
            pos_info[cohort_pos] = f"Win Pct: {round(cohort_win_pct, 2)}%"
            pos_cohort[cohort_pos] = team_list
            for tm in cohort:
                games = tm.get_opps_games(cohort)  # list[TournGame]
                cohort_rpt[tm] = games
                team_list.append(team_tag(tm))

            # this is stupid, but we have to rederive the ranking results just to get
            # access to the intermediary results (i.e. `elevs` and `win_grps`)--but at
            # least we can validate against the initially computed (and saved) rankings,
            # to make sure this is right
            ranked, _, _ = rank_team_cohort(cohort)  # returns with elevations undone
            ranked, elevs, win_grps, _ = elevate_winners(ranked)
            for i, tm in enumerate(ranked):
                assert cohort_pos + i == tm.div_rank
            idents = Team.ident_div_tbs(div, cohort_pos)
            pos_elevs[cohort_pos] = elevs
            pos_win_grps[cohort_pos] = win_grps
            pos_idents[cohort_pos] = idents

    # REVISIT: still not sure where all of this formatting stuff should be consolidated
    # (but this is okay for now)!!!
    concat_seeds = lambda x: ' - '.join(f"{tm.div_seed}" for tm in x)
    concat_teams = lambda x: ' - '.join(f"{tm.team_name} ({tm.div_seed})" for tm in x)

    context = {
        'report_num'  : 1,
        'title'       : RR_TB_REPORT,
        'tourn'       : tourn,
        'len'         : len,
        'round'       : round,
        'div_rpt'     : div_rpt,
        'div_info'    : div_info,
        'div_cohort'  : div_cohort,
        'div_elevs'   : div_elevs,
        'div_win_grps': div_win_grps,
        'div_idents'  : div_idents,
        'concat_seeds': concat_seeds,
        'concat_teams': concat_teams,
        'report_by'   : 'team'
    }
    return render_report(context)
