# -*- coding: utf-8 -*-

"""Blueprint for the mobile device interface
"""
from typing import NamedTuple
import re
from http import HTTPStatus

from flask import (Blueprint, request, render_template, abort, redirect, url_for, flash,
                   get_flashed_messages)
from flask_login import current_user
from ckautils import typecast

from schema import (GAME_PTS, BRACKET_SEED, BRACKET_TOURN, TournStage, TournInfo, SeedGame,
                    TournGame, PostScore, SCORE_SUBMIT, SCORE_ACCEPT, SCORE_CORRECT,
                    SCORE_IGNORE, SCORE_DISCARD)
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

def same_score(s1: PostScore | tuple[int, int], s2: PostScore) -> bool:
    """Check if two scores are equal.  `s1` may be specified as a `PostScore` instance or
    a tuple of (team1_pts, team2_pts).
    """
    if isinstance(s1, tuple):
        assert len(s1) == 2
        return s1 == (s2.team1_pts, s2.team2_pts)
    else:
        assert isinstance(s1, PostScore)
        return (s1.team1_pts, s1.team2_pts) == (s2.team1_pts, s2.team2_pts)

# just downcase the first character and leave the rest alone
lc_first = lambda x: x[0].lower() + x[1:]

##############
# GET routes #
##############

@mobile.get("/mobile")
def index() -> str:
    """Render mobile app if logged in
    """
    if not current_user.is_authenticated:
        flash("Please reauthenticate in order to access the app")
        return redirect('/login')

    err_msg = "<br>".join(get_flashed_messages())
    context = {'err_msg': err_msg}
    return render_mobile(context)

################
# POST actions #
################

ACTIONS = [
    'submit_score',
    'accept_score',
    'correct_score'
]

@mobile.post("/mobile")
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
    """Submit game score.  This score will need to be accepted in order to be pushed to
    the appropriate bracket.

    Note that multiple players may submit scores (if app not refreshed).  If a subsequent
    submission contains the same team scores, it will be treated as an "accept" if coming
    from an opponent, or ignored as a duplicate if coming from a partner.  If the team
    scores do not match, then it will be treated as a "correct" coming from a member of
    either team.
    """
    post_action = SCORE_SUBMIT
    action_info = None
    game_label  = form['game_label']
    player_num  = typecast(form['posted_by_num'])
    team_idx    = typecast(form['team_idx'])
    team1_pts   = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts   = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

    ref_score_id = typecast(form['ref_score_id'])
    if ref_score_id is not None:
        abort(400, f"ref_score_id ({ref_score_id}) should not be set")
    if max(team1_pts, team2_pts) < GAME_PTS:
        flash("Only completed games may be submitted")
        return redirect(url_for('index'))
    if (team1_pts, team2_pts) == (GAME_PTS, GAME_PTS):
        flash(f"Only one team can score {GAME_PTS} points")
        return redirect(url_for('index'))

    # see if someone slid in ahead of us (can't be ourselves)
    latest = PostScore.get_last(game_label)
    if latest:
        if same_score((team1_pts, team2_pts), latest):
            if latest.team_idx != team_idx:
                flash("Duplicate submission as opponent treated as acceptance")
                return accept_score(form)
            # otherwise we fall through and create an ignored duplicate entry
            post_action += SCORE_IGNORE
            action_info = "Duplicate submission (as partner)"
            flash(f"Ignoring {lc_first(action_info)}")
        else:
            # correct the score, whether partner or opponent
            return correct_score(form, latest)

    info = {
        'bracket'      : get_bracket(game_label),
        'game_label'   : game_label,
        'post_action'  : post_action,
        'action_info'  : action_info,
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
    """Accept a game score posted by an opponent.

    If an intervening correction from an opponent has the same score as the original
    reference, then switch the acceptance to the newer record, otherwise intervening
    changes invalidate this request.
    """
    post_action = SCORE_ACCEPT
    action_info = None
    game_label = form['game_label']
    player_num = typecast(form['posted_by_num'])
    team_idx   = typecast(form['team_idx'])
    team1_pts  = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts  = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

    ref_score_id = typecast(form['ref_score_id'])
    ref_score = PostScore.get_or_none(ref_score_id)
    if not ref_score:
        abort(400, f"invalid ref_score_id {ref_score_id}")
    assert same_score((team1_pts, team2_pts), ref_score)

    # check for intervening corrections
    latest = PostScore.get_last(game_label)
    if latest != ref_score:
        assert latest.created_at > ref_score.created_at
        if same_score(latest, ref_score):
            if latest.team_idx != team_idx:
                # same score correction from opponent
                ref_score = latest
                action_info = f"Changing ref_score from id {ref_score_id} to id {latest.id}"
            else:
                # same score correction from partner
                post_action += SCORE_DISCARD
                action_info = "Intervening correction (same score)"
                flash(f"Discarding acceptance due to {lc_first(action_info)}")
        else:
            # changed score correction (from either partner or opponent)
            post_action += SCORE_DISCARD
            action_info = "Intervening correction"
            flash(f"Discarding acceptance due to {lc_first(action_info)}")

    info = {
        'bracket'      : get_bracket(game_label),
        'game_label'   : game_label,
        'post_action'  : post_action,
        'action_info'  : action_info,
        'team1_pts'    : team1_pts,
        'team2_pts'    : team2_pts,
        'posted_by_num': player_num,
        'team_idx'     : team_idx,
        'ref_score'    : ref_score,
        'do_push'      : True
    }
    score = PostScore.create(**info)
    if post_action == SCORE_ACCEPT:
        try:
            score.push_scores()
        except RuntimeError as e:
            flash(str(e))
            return redirect(url_for('index'))

    return redirect(url_for('index'))

def correct_score(form: dict, ref: PostScore = None) -> str:
    """Correct a game score, superceding all previous submitted (or corrected) scores.  As
    with "submit", this score will need to be accepted in order to be pushed.  This can be
    called on behalf of either team.

    If the specified score is identical to the reference entry, this correction will be
    treated as an acceptance if coming from an opponent, or will be ignored if coming from
    a partner.
    """
    post_action = SCORE_CORRECT
    action_info = None
    game_label = form['game_label']
    player_num = typecast(form['posted_by_num'])
    team_idx   = typecast(form['team_idx'])
    team1_pts  = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts  = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

    ref_score_id = typecast(form['ref_score_id'])
    ref_score = PostScore.get_or_none(ref_score_id)
    if not ref_score:
        abort(400, f"invalid ref_score_id {ref_score_id}")
    if max(team1_pts, team2_pts) < GAME_PTS:
        flash("Only completed games may be submitted")
        return redirect(url_for('index'))
    if (team1_pts, team2_pts) == (GAME_PTS, GAME_PTS):
        flash(f"Only one team can score {GAME_PTS} points")
        return redirect(url_for('index'))

    # check for intervening corrections
    latest = PostScore.get_last(game_label)
    if latest != ref_score:
        assert latest.created_at > ref_score.created_at
        # NOTE that we are always discarding this action if there is an intervening
        # correction (regardless of actor and score), since the logic for implicit
        # acceptance could be messy and/or counterintuitive
        if same_score(latest, ref_score):
            post_action += SCORE_DISCARD
            action_info = "Intervening correction (same score)"
            flash(f"Discarding update due to {lc_first(action_info)}")
        else:
            post_action += SCORE_DISCARD
            action_info = "Intervening correction"
            flash(f"Discarding update due to {lc_first(action_info)}")

    if same_score((team1_pts, team2_pts), ref_score):
        if ref_score.team_idx != team_idx:
            flash("Unchanged score correction treated as acceptance")
            return accept_score(form)
        # otherwise we fall through and create an ignored correction entry
        post_action += SCORE_IGNORE
        action_info = "Unchanged score (as partner)"
        flash(f"Ignoring {lc_first(action_info)}")

    info = {
        'bracket'      : get_bracket(game_label),
        'game_label'   : game_label,
        'post_action'  : post_action,
        'action_info'  : action_info,
        'team1_pts'    : team1_pts,
        'team2_pts'    : team2_pts,
        'posted_by_num': player_num,
        'team_idx'     : team_idx,
        'ref_score'    : ref_score,
        'do_push'      : False
    }
    score = PostScore.create(**info)
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
