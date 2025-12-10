#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Blueprint for report rendering
"""
from itertools import groupby

from flask import Blueprint, session, render_template, abort

from schema import GAME_PTS, TournInfo, Player, PlayerGame, Team, TeamGame
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

def sd_tb_report(tourn: TournInfo) -> str:
    """Render seeding round tie-breaker report
    """
    return render_report({})

################
# rr_tb_report #
################

def rr_tb_report(tourn: TournInfo) -> str:
    """Render round robin tie-breaker report
    """
    div_iter = range(1, tourn.divisions + 1)
    tm_list = Team.get_team_map().values()
    by_rank = sorted(tm_list, key=lambda x: x.div_rank)

    # report keys for each layer: div (int), cohort_pos (int), team (Team) -> TournGames
    div_reports = {}
    for div in div_iter:
        pos_rpt = {}
        div_reports[div] = pos_rpt

        div_teams = list(filter(lambda x: x.div_num == div, by_rank))
        for k, g in groupby(div_teams, key=lambda x: x.div_pos):
            cohort = list(g)
            if len(cohort) == 1:
                continue
            cohort_pos = cohort[0].div_pos
            cohort_rpt = {}
            pos_rpt[cohort_pos] = cohort_rpt
            for tm in cohort:
                # get player TeamGame.join(TournGame) records vs. cohort opps
                games = tm.get_opps_games(cohort)
                cohort_rpt[tm] = games

                # format games data (highlight current team)
                
                # check for/flag conflicts (loss to lower-ranked cohort)

                # check for/flag absolute ties (identical tb_crit values)

    context = {
        'report_num' : 1,
        'title'      : RR_TB_REPORT,
        'tourn'      : tourn,
        'len'        : len,
        'round'      : round,
        'div_reports': div_reports,
        'report_by'  : 'team'
    }
    return render_report(context)
