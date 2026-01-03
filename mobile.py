# -*- coding: utf-8 -*-

"""Blueprint for the mobile device interface
"""
from typing import NamedTuple
import re
from http import HTTPStatus

from flask import Blueprint, request, session, render_template, redirect, url_for, flash
from flask_login import current_user

from schema import TournStage, TournInfo

###################
# blueprint stuff #
###################

mobile = Blueprint('mobile', __name__)
MOBILE_TITLE = "Euchmgr"
MOBILE_TEMPLATE = "mobile.html"
ERROR_TEMPLATE = "error.html"

#################
# utility stuff #
#################

MOBILE_REGEX = r'Mobile|Android|iPhone'

def is_mobile() -> bool:
    """Determine mobile client by the user-agent string
    """
    return re.search(MOBILE_REGEX, request.user_agent.string) is not None

class UserInfo(NamedTuple):
    """Readonly user info/stats field
    """
    name   : str  # also used as the element id
    cls    : str  # CSS class for info data span
    label  : str
    min_stg: TournStage

##############
# GET routes #
##############

@mobile.get("/")
def index() -> str:
    """Render mobile app if logged in
    """
    if not current_user.is_authenticated:
        flash("Please reauthenticate in order to access the app")
        return redirect('/login')

    context = {}
    return render_mobile(context)

################
# POST actions #
################

#############
# renderers #
#############

INFO_FIELDS = [
    UserInfo("tourn",     "wide", "Tournament",    TournStage.TOURN_CREATE),
    UserInfo("plyr_num",  "",     "Player Num",    TournStage.TOURN_CREATE),
    UserInfo("seed_rank", "",     "Player Rank",   TournStage.TOURN_CREATE),
    UserInfo("team_name", "wide", "Team Name",     TournStage.TOURN_TEAMS),
    UserInfo("div_num",   "",     "Division",      TournStage.TOURN_BRACKET),
    UserInfo("div_seed",  "",     "Seed (div)",    TournStage.TOURN_BRACKET),
    UserInfo("stage",     "med",  "Stage",         TournStage.TOURN_CREATE),
    UserInfo("round",     "",     "Game #",        TournStage.TOURN_CREATE),
    UserInfo("win_rec",   "",     "W-L (stage)",   TournStage.TOURN_CREATE),
    UserInfo("pts_rec",   "",     "PF-PA (stage)", TournStage.TOURN_CREATE)
]

DONE_PLAYING = "<i>(done)</i>"

def render_mobile(context: dict) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    tourn = TournInfo.get()
    player = current_user
    team = current_user.team

    if tourn.stage_start >= TournStage.TOURN_RESULTS:
        cur_stage = "Round Robin"
        cur_game = team.current_game
        cur_round = cur_game.round_num if cur_game else DONE_PLAYING
        win_rec = f"{team.tourn_wins}-{team.tourn_losses}"
        pts_rec = f"{team.tourn_pts_for}-{team.tourn_pts_against}"
    elif tourn.stage_start >= TournStage.SEED_RESULTS:
        cur_stage = "Seeding"
        cur_game = player.current_game
        cur_round = cur_game.round_num if cur_game else DONE_PLAYING
        win_rec = f"{player.seed_wins}-{player.seed_losses}"
        pts_rec = f"{player.seed_pts_for}-{player.seed_pts_against}"
    else:
        cur_stage = None
        cur_game = None
        cur_round = None
        win_rec = None
        pts_rec = None

    info_data = [
        tourn.name,
        player.player_num,
        player.player_rank,
        team.team_name if team else None,
        team.div_num if team else None,
        team.div_seed if team else None,
        cur_stage,
        cur_round,
        win_rec,
        pts_rec
    ]
    assert len(info_data) == len(INFO_FIELDS)

    no_team = lambda x: not x.if_team
    base_ctx = {
        'title'    : MOBILE_TITLE,
        'tourn'    : tourn,
        'user'     : current_user,
        'team'     : team,
        'info_flds': INFO_FIELDS,
        'info_data': info_data,
        'cur_game' : cur_game,
        'err_msg'  : None
    }
    return render_template(MOBILE_TEMPLATE, **(base_ctx | context))

def render_error(code: int, name: str = None, desc: str = None) -> str:
    """Mobile-adjusted error page (replacement for `flask.abort`)
    """
    err = HTTPStatus(code)
    context = {
        'title'      : f"{code} {err._name_}",
        'error'      : name or err.phrase,
        'description': desc or err.description
    }
    return render_template(ERROR_TEMPLATE, **context), code
