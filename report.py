# -*- coding: utf-8 -*-

"""Blueprint for report rendering
"""
from itertools import groupby

from flask import Blueprint, session, render_template, abort

from schema import GAME_PTS, TournInfo, Player, PlayerGame, Team, TeamGame, PostScore
from euchmgr import Elevs, TeamGrps, rank_team_cohort, elevate_winners, get_game_by_label
from chart import Numeric, round_val, fmt_tally

###################
# blueprint stuff #
###################

report = Blueprint('report', __name__)
REPORT_TEMPLATE = "report.html"
POPUP_TEMPLATE = "popup.html"

TIE_BREAKER = "Round Robin Tie-Breaker Report"
SCORE_POSTING = "Score Posting Report"

REPORT_FUNCS = [
    'tie_breaker',
    'score_posting'
]

@report.get("/<report>")
def get_report(report: str) -> str:
    """Render specified report
    """
    if report not in REPORT_FUNCS:
        abort(404, f"Invalid report func '{report}'")

    tourn = TournInfo.get(requery=True)
    return globals()[report](tourn)

@report.get("/<report>/<target>")
def get_report_targ(report: str, target: str) -> str:
    """Render specified report (with target)
    """
    if report not in REPORT_FUNCS:
        abort(404, f"Invalid report func '{report}'")

    tourn = TournInfo.get(requery=True)
    return globals()[report](target, tourn)

def render_report(context: dict) -> str:
    """Render full-sized report
    """
    return render_template(REPORT_TEMPLATE, **context)

def render_popup(context: dict) -> str:
    """Render mini (popup) report
    """
    return render_template(POPUP_TEMPLATE, **context)

################
# tie_breaker #
################

# HORRIBLY HACKY: this same format func is hacked into schema.py a few places (as well as
# in fmt_team_name [euchmgr.py])--we really need to refactor/consolidate all of this!!!
team_tag = lambda x: f"{x.team_name} [{x.div_seed}]"

def tie_breaker(tourn: TournInfo) -> str:
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
    concat_teams = lambda x: ' - '.join(f"{tm.team_name} [{tm.div_seed}]" for tm in x)

    context = {
        'report_num'  : 0,
        'title'       : TIE_BREAKER,
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

#################
# score_posting #
#################

def score_posting(game_label: str, tourn: TournInfo) -> str:
    """Render score posting report (as a popup)
    """
    game = get_game_by_label(game_label)
    posts = PostScore.get_posts(game_label)

    context = {
        'popup_num': 0,
        'title'    : SCORE_POSTING,
        'tourn'    : tourn,
        'game'     : game,
        'posts'    : posts
    }
    return render_popup(context)
