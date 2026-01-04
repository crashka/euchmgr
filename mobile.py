# -*- coding: utf-8 -*-

"""Blueprint for the mobile device interface
"""
from typing import NamedTuple
import re
from http import HTTPStatus

from flask import Blueprint, request, render_template, redirect, url_for, flash, abort
from flask_login import current_user
from ckautils import typecast

from schema import (BRACKET_SEED, BRACKET_TOURN, TournStage, TournInfo, SeedGame, TournGame,
                    PostScore)
from euchmgr import PFX_SEED, PFX_TOURN

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

def stage_status(games: SeedGame | TournGame) -> str:
    """Return current stage status/round
    """
    cur_round = games.current_round()
    if cur_round == 0:
        return "Not Started"
    elif cur_round == -1:
        return "Done"
    else:
        return f"Round {cur_round}"

def get_bracket(label: str) -> str:
    """Get name of bracket based on game label.  FIX: quick and dirty for now--need to
    consolidate this with PFX_ and BRACKET_ declarations!!!
    """
    pfx = label.split('-', 1)[0]
    if pfx == 'sd':
        return BRACKET_SEED
    elif pfx == 'rr':
        return BRACKET_TOURN
    assert False, "Logic error"

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

ACTIONS = [
    'submit_score',
    'accept_score',
    'correct_score'
]

@mobile.post("/")
def submit() -> str:
    """Handle post action
    """
    if 'action' not in request.form:
        abort(400, "Invalid request, no action specified")
    action = request.form['action']
    if action not in ACTIONS:
        abort(400, f"Invalid request, unrecognized action '{action}'")
    return globals()[action](request.form)

def submit_score(form: dict) -> str:
    """Submit game score.

    Note that multiple players may submit scores (if app not refreshed).  If a subsequent
    submission contains the same team scores, it will be treated as an "accept" if coming
    from an opponent, or be saved as a duplicate if coming from a partner (no harm--either
    entry may be accepted by opponents).  If the team scores do not match, then it will be
    treated as a "correct" coming from a member of either team.
    """
    game_label = form['game_label']
    player_num = typecast(form['posted_by_num'])
    team_idx   = typecast(form['team_idx'])
    team1_pts  = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts  = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

    ref_score_id = typecast(form['ref_score_id'])
    if ref_score_id is not None:
        abort(400, f"ref_score_id ({ref_score_id}) should not be set")

    info = {
        'bracket'      : get_bracket(game_label),
        'game_label'   : game_label,
        'post_action'  : "submit",
        'team1_pts'    : team1_pts,
        'team2_pts'    : team2_pts,
        'posted_by_num': player_num,
        'team_idx'     : team_idx,
        'ref_score'    : None,
        'do_push'      : False
    }
    score = PostScore.create(**info)
    return redirect(url_for('index'))

def accept_score(form: dict) -> str:
    """Create new tournament from form data.
    """
    game_label = form['game_label']
    player_num = typecast(form['posted_by_num'])
    team_idx   = typecast(form['team_idx'])
    team1_pts  = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts  = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

    ref_score_id = typecast(form['ref_score_id'])
    ref_score = PostScore.get_or_none(ref_score_id)
    if not ref_score:
        abort(400, f"invalid ref_score_id {ref_score_id}")
    assert team1_pts == ref_score.team1_pts
    assert team2_pts == ref_score.team2_pts

    info = {
        'bracket'      : get_bracket(game_label),
        'game_label'   : game_label,
        'post_action'  : "accept",
        'team1_pts'    : team1_pts,
        'team2_pts'    : team2_pts,
        'posted_by_num': player_num,
        'team_idx'     : team_idx,
        'ref_score'    : ref_score,
        'do_push'      : True
    }
    score = PostScore.create(**info)
    score.push_scores()
    return redirect(url_for('index'))

def correct_score(form: dict) -> str:
    """Create new tournament from form data.
    """
    return redirect(url_for('index'))

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
    UserInfo("status",    "",     "Status",        TournStage.TOURN_CREATE),
    UserInfo("win_rec",   "",     "W-L (stage)",   TournStage.TOURN_CREATE),
    UserInfo("pts_rec",   "",     "PF-PA (stage)", TournStage.TOURN_CREATE)
]

def render_mobile(context: dict) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    tourn  = TournInfo.get()
    player = current_user
    team   = current_user.team

    if tourn.stage_start >= TournStage.TOURN_RESULTS:
        assert team
        cur_stage = "Round Robin"
        cur_game  = team.current_game
        status    = stage_status(TournGame)
        team_idx  = cur_game.team_idx(team) if cur_game else None
        win_rec   = f"{team.tourn_wins}-{team.tourn_losses}"
        pts_rec   = f"{team.tourn_pts_for}-{team.tourn_pts_against}"
    elif tourn.stage_start >= TournStage.SEED_RESULTS:
        cur_stage = "Seeding"
        cur_game  = player.current_game
        status    = stage_status(SeedGame)
        team_idx  = cur_game.player_team_idx(player) if cur_game else None
        win_rec   = f"{player.seed_wins}-{player.seed_losses}"
        pts_rec   = f"{player.seed_pts_for}-{player.seed_pts_against}"
    else:
        cur_stage = None
        cur_game  = None
        status    = None
        team_idx  = None
        win_rec   = None
        pts_rec   = None

    if team_idx in (0, 1):
        opp_idx   = team_idx ^ 0x01
        team_tag  = cur_game.team_tags[team_idx]
        team_pts  = cur_game.team1_pts if team_idx == 0 else cur_game.team2_pts
        opp_tag   = cur_game.team_tags[opp_idx]
        opp_pts   = cur_game.team1_pts if opp_idx == 0 else cur_game.team2_pts
    else:
        opp_idx   = None
        team_tag  = None
        team_pts  = None
        opp_tag   = None
        opp_pts   = None

    info_data = [
        tourn.name,
        player.player_num,
        player.player_rank,
        team.team_name if team else None,
        team.div_num if team else None,
        team.div_seed if team else None,
        cur_stage,
        status,
        win_rec,
        pts_rec
    ]
    assert len(info_data) == len(INFO_FIELDS)

    ref_score = None
    if cur_game and not cur_game.winner:
        ref_score = PostScore.get_last(cur_game.label)
        if ref_score:
            team_pts = ref_score.team1_pts if team_idx == 0 else ref_score.team2_pts
            opp_pts = ref_score.team1_pts if opp_idx == 0 else ref_score.team2_pts

    no_team = lambda x: not x.if_team
    base_ctx = {
        'title'       : MOBILE_TITLE,
        'tourn'       : tourn,
        'user'        : current_user,
        'team'        : team,
        'team_idx'    : team_idx,
        'info_flds'   : INFO_FIELDS,
        'info_data'   : info_data,
        'cur_game'    : cur_game,
        'team_tag'    : team_tag,
        'team_pts'    : team_pts,
        'opp_tag'     : opp_tag,
        'opp_pts'     : opp_pts,
        'ref_score'   : ref_score,
        'ref_score_id': ref_score.id if ref_score else None,
        'err_msg'     : None
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
