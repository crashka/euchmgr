# -*- coding: utf-8 -*-

"""Blueprint for the mobile device interface
"""
from typing import NamedTuple
import re
from http import HTTPStatus

from peewee import IntegrityError
from flask import (Blueprint, request, render_template, abort, redirect, url_for, flash,
                   get_flashed_messages)
from ckautils import typecast

from core import ImplementationError, LogicError
from security import current_user
from schema import GAME_PTS, Bracket, TournStage, TournInfo, ScoreAction
from euchmgr import compute_player_ranks, compute_team_ranks, compute_playoff_ranks
from ui import (fmt_pct, PTS_PCT_NA, get_bracket, get_game_by_label, Player, PlayerRegister,
                PartnerPick, SeedGame, Team, TournGame, PlayoffGame, PostScore)

###################
# blueprint stuff #
###################

mobile = Blueprint('mobile', __name__)
MOBILE_TITLE = "Euchmgr"
MOBILE_TEMPLATE = "mobile.html"
ERROR_TEMPLATE = "error.html"
MOBILE_URL_PFX = '/mobile'

#################
# utility stuff #
#################

MOBILE_REGEX = r'Mobile|Android|iPhone'

def is_mobile() -> bool:
    """Determine mobile client by the user-agent string
    """
    return re.search(MOBILE_REGEX, request.user_agent.string) is not None

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

def fmt_matchup(game: SeedGame | TournGame, ref: Player | Team) -> tuple[str, str, str]:
    """Return formatted matchup representation (teams and scores) as HTML blocks to be
    rendered side-by-side (same look as bracket charts).
    """
    team_idx = game.team_idx(ref)
    if team_idx == -1:
        # player or team has a bye
        if isinstance(ref, Player):
            matchup = ref.player_tag
        else:
            assert isinstance(ref, Team)
            matchup = ref.team_tag
        scores = "<span><i>bye</i></span>"
        units = ""
        return matchup, scores, units

    assert team_idx in (0, 1)
    opp_idx = team_idx ^ 0x01
    if game.winner:
        pts_arr = [game.team1_pts, game.team2_pts]
        cls_arr = ['winner', 'loser'] if game.team1_pts == GAME_PTS else ['loser', 'winner']
    else:
        pts_arr = ['&nbsp;', '&nbsp;']
        cls_arr = ['', '']
    matchup = (f"<span class=\"{cls_arr[team_idx]}\">{game.team_tags[team_idx]}</span><br>vs.<br>"
               f"<span>{game.team_tags[opp_idx]}</span>")
    scores = (f"<span class=\"{cls_arr[team_idx]}\">{pts_arr[team_idx]}</span><br><br>"
              f"<span>{pts_arr[opp_idx]}</span>")
    units = "<label>pts</label><br><br><label>pts</label>"
    return matchup, scores, units


def fmt_rec(x: int, y: int, team_idx: int = 0) -> str:
    """Format a record string given two input values (e.g. wins and losses, or points for
    and against).  We put them in the correct order given a team index of either 0 or 1.
    """
    assert team_idx in (0, 1)
    return f"{x}-{y}" if team_idx == 0 else f"{y}-{x}"

def post_info(post: PostScore, team_idx: int = 0) -> str:
    """Return formatted information about a posted score (teams' points and player
    posting), from the perspective of the specified team index.
    """
    score = fmt_rec(post.team1_pts, post.team2_pts, team_idx)
    poster = post.posted_by.name
    action = "accepted" if post.post_action == ScoreAction.ACCEPT else "posted"
    return f"{poster} {action} a score of '{score}'"

def get_leaderboard(bracket: str, div: int = None) -> list[tuple[int, str, str, str, str]]:
    """Return tuples of (id, player/team tag, W-L, pts_pct, rank) ordered by rank.  `div`
    must be specified for Bracket.TOURN.
    """
    if bracket == Bracket.SEED:
        pl_list = list(Player.iter_players(by_rank=True))
        return [(pl.id, pl.player_tag, fmt_rec(pl.seed_wins, pl.seed_losses),
                 fmt_pct(pl.seed_pts_pct or PTS_PCT_NA), pl.player_rank or "")
                for pl in pl_list]
    elif bracket == Bracket.TOURN:
        assert div
        tm_list = list(Team.iter_teams(div=div, by_rank=True))
        return [(tm.id, tm.team_tag, fmt_rec(tm.tourn_wins, tm.tourn_losses),
                 fmt_pct(tm.tourn_pts_pct or PTS_PCT_NA), tm.div_rank or "")
                for tm in tm_list]
    elif bracket == Bracket.SEMIS:
        tm_list = list(Team.iter_playoff_teams(by_rank=True))
        return [(tm.id, tm.team_tag_pl, fmt_rec(tm.playoff_wins, tm.playoff_losses),
                 fmt_pct(tm.playoff_pts_pct or PTS_PCT_NA), tm.playoff_rank or "")
                for tm in tm_list]
    elif bracket == Bracket.FINALS:
        tm_list = list(Team.iter_finals_teams(by_rank=True))
        return [(tm.id, tm.team_tag_pl, fmt_rec(tm.playoff_wins, tm.playoff_losses),
                 fmt_pct(tm.playoff_pts_pct or PTS_PCT_NA), tm.playoff_rank or "")
                for tm in tm_list]
    raise LogicError(f"unknown bracket '{bracket}'")

def update_rankings(bracket: str) -> bool:
    """Update rankings for the specified bracket.  The return value indicates whether this
    call synchronous performed the update (otherwise, the execution is assumed deferred).

    REVISIT: this is kind of code-heavy, so we may not want to do it every time a score is
    posted--if we find updates tripping over each other, we can create a global timestamp
    to ensure that updates are appropriate spaced!!!

    """
    if bracket == Bracket.SEED:
        compute_player_ranks()
    elif bracket == Bracket.TOURN:
        compute_team_ranks()
    else:
        assert bracket in (Bracket.SEMIS, Bracket.FINALS)
        compute_playoff_ranks(bracket)
    return True

def update_tourn_stage(bracket: Bracket) -> bool:
    """Mark the current tournament stage complete if all games/picks are done.

    ATTN: this is getting kind of ugly--really need to declare the relationship between
    Bracket and TournStage (and reconcile with BRACKET_GAME_CLS in euchmgr.py) and do this
    all more cleanly!!!
    """
    if bracket == Bracket.SEED:
        if SeedGame.current_round() == -1:
            TournInfo.mark_stage_complete(TournStage.SEED_RESULTS)
    elif bracket == Bracket.TOURN:
        if TournGame.current_round() == -1:
            TournInfo.mark_stage_complete(TournStage.TOURN_RESULTS)
    else:
        assert bracket in (Bracket.SEMIS, Bracket.FINALS)
        if PlayoffGame.current_round(bracket) == -1:
            stage = (TournStage.SEMIS_RESULTS if bracket == Bracket.SEMIS
                     else TournStage.FINALS_RESULTS)
            TournInfo.mark_stage_complete(stage)
    return True

##############
# GET routes #
##############

VIEW_INDEX       = './'
VIEW_REGISTER    = 'register'
VIEW_SEEDING     = 'seeding'
VIEW_PARTNERS    = 'partners'
VIEW_ROUND_ROBIN = 'round_robin'
VIEW_SEMIFINALS  = 'semifinals'
VIEW_FINALS      = 'finals'

BRACKET_VIEW = {
    Bracket.SEED  : VIEW_SEEDING,
    Bracket.TOURN : VIEW_ROUND_ROBIN,
    Bracket.SEMIS : VIEW_SEMIFINALS,
    Bracket.FINALS: VIEW_FINALS
}

STAGE_VIEW = [
    (TournStage.SEMIS_RANKS,  VIEW_FINALS),
    (TournStage.TOURN_RANKS,  VIEW_SEMIFINALS),
    (TournStage.TOURN_TEAMS,  VIEW_ROUND_ROBIN),
    (TournStage.SEED_RANKS,   VIEW_PARTNERS),
    (TournStage.SEED_BRACKET, VIEW_SEEDING),
    (TournStage.PLAYER_NUMS,  VIEW_REGISTER)
]

def remap_view(view: str, player: Player) -> str:
    """Remap playoff views back to main tournament (or earlier playoff round) for players
    with no games in the specified view.
    """
    team = player.team  # may be `None` if teams not yet picked
    if view == VIEW_FINALS and not (team and team.finals_team):
        if team and team.playoff_team:
            return VIEW_SEMIFINALS
        return VIEW_ROUND_ROBIN
    elif view == VIEW_SEMIFINALS and not (team and team.playoff_team):
        return VIEW_ROUND_ROBIN
    return view

def dflt_view(tourn: TournInfo, player: Player) -> str:
    """Return most relevant view for the current stage of the tournament
    """
    assert tourn.stage_start
    for stage, view in STAGE_VIEW:
        if tourn.stage_start >= stage:
            return remap_view(view, player)
    raise LogicError(f"unexpected stage_start '{tourn.stage_start}'")

@mobile.get("/")
def index() -> str:
    """Render mobile app if logged in
    """
    if not current_user.is_authenticated:
        flash("Please reauthenticate in order to access the app")
        return redirect(url_for('login_page'))

    tourn = TournInfo.get()
    view = dflt_view(tourn, current_user)
    assert view
    # REVISIT: we should figure out if we need to forward these on--they may stayed
    # queued through the redirect!!!
    for msg in get_flashed_messages():
        flash(msg)
    return render_view(view)

@mobile.get("/register")
@mobile.get("/seeding")
@mobile.get("/partners")
@mobile.get("/round_robin")
@mobile.get("/semifinals")
@mobile.get("/finals")
def view() -> str:
    """Render mobile app if logged in
    """
    if not current_user.is_authenticated:
        flash("Please reauthenticate in order to access the app")
        return redirect(url_for('login_page'))
    view = request.path.split('/')[-1]

    context = {}
    game_label = None
    err_msgs = []
    # see if any secret parameters have been transmitted to us--NOTE that parameter name
    # and action are currently hard-coded here (since we are only supporting one!); we may
    # create a little more structure around this later, if needed
    for msg in get_flashed_messages():
        if m := re.fullmatch(r'(\w+)=(.+)', msg):
            key, val = m.group(1, 2)
            if key == 'cur_game':
                assert not request.args.get('cur_game')
                game_label = val
            else:
                raise ImplementationError(f"unexpected secret key '{key}' (value '{val}')")
        else:
            err_msgs.append(msg)
    context['err_msg'] = "<br>".join(err_msgs)

    if not game_label:
        game_label = request.args.get('cur_game')

    if game_label:
        cur_game = get_game_by_label(game_label)
        assert cur_game
        # pass it on to the renderer so we can highlight it on the page
        context['cur_game'] = cur_game

    return render_mobile(context, view)

################
# POST actions #
################

ACTIONS = [
    'register_player',
    'submit_score',
    'accept_score',
    'correct_score',
    'pick_partner'
]

@mobile.post("/")
def submit() -> str:
    """Handle post action
    """
    if not current_user.is_authenticated:
        abort(403, f"Not authenticated")
    if 'action' not in request.form:
        abort(400, "Invalid request, no action specified")
    action = request.form['action']
    if action not in ACTIONS:
        abort(400, f"Invalid request, unrecognized action '{action}'")
    return globals()[action](request.form)

def register_player(form: dict) -> str:
    """Complete the registration for a player, which entails entering the "player num"
    (ping pong ball number) and specifying (or confirming) the nick name.
    """
    player_id  = typecast(form['player_id'])
    player_num = typecast(form.get('player_num', ""))  # no key means not selected
    nick_name  = typecast(form['nick_name'])
    player     = Player.get(player_id)

    if not player_num:
        assert not player.player_num
        # show message, but store the record anyway
        flash("Player Num must be specified")
    else:
        player.player_num = player_num
    player.nick_name = nick_name  # allow nick_name to be nulled out
    try:
        player.save()
    except IntegrityError as e:
        flash("Player Num already taken")
    return render_view(VIEW_REGISTER)

def submit_score(form: dict) -> str:
    """Submit game score.  This score will need to be accepted in order to be pushed to
    the appropriate bracket.

    Note that multiple players may submit scores (if app not refreshed).  If a subsequent
    submission contains the same team scores, it will be treated as an "accept" if coming
    from an opponent, or ignored as a duplicate if coming from a partner.  If the team
    scores do not match, then it will be treated as a "correct" coming from a member of
    either team.
    """
    post_action  = ScoreAction.SUBMIT
    action_info  = None
    game_label   = form['game_label']
    bracket      = get_bracket(game_label)
    player_num   = typecast(form['posted_by_num'])
    team_idx     = typecast(form['team_idx'])
    team1_pts    = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts    = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])
    score_pushed = None

    ref_score_id = typecast(form['ref_score_id'])
    if ref_score_id is not None:
        abort(400, f"ref_score_id ({ref_score_id}) should not be set")
    # these should be enforced by the UI
    assert max(team1_pts, team2_pts) == GAME_PTS
    assert (team1_pts, team2_pts) != (GAME_PTS, GAME_PTS)

    # see if someone slid in ahead of us (can't be ourselves)
    latest = PostScore.get_last(game_label, include_accept=True)
    if latest:
        if latest.post_action == ScoreAction.ACCEPT:
            score_pushed = True
            post_action += ScoreAction.DISCARD
            action_info = "Intervening acceptance"
            flash(f"Discarding submission due to {lc_first(action_info)} "
                  f"({post_info(latest, team_idx)})")
        elif same_score((team1_pts, team2_pts), latest):
            if latest.team_idx != team_idx:
                flash("Duplicate submission as opponent treated as mutual acceptance "
                      f"({post_info(latest, team_idx)})")
                return accept_score(form, latest)
            # otherwise we fall through and create an ignored duplicate entry
            post_action += ScoreAction.IGNORE
            action_info = "Duplicate submission as partner"
            flash(f"Ignoring {lc_first(action_info)} ({post_info(latest, team_idx)})")
        else:
            # NOTE: we previously overwrote a mismatched prior submission, but I think
            # that is both less intuitive and less desirable, so we'll intercept this
            # submission instead
            post_action += ScoreAction.DISCARD
            action_info = "Conflicting submission"
            flash(f"Discarding {lc_first(action_info)} ({post_info(latest, team_idx)})")

    info = {
        'bracket'      : bracket,
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
    if score_pushed:
        return render_game_in_view(game_label)
    return render_view(BRACKET_VIEW[bracket])

def accept_score(form: dict, ref_score: PostScore = None) -> str:
    """Accept a game score posted by an opponent.

    If an intervening correction from an opponent has the same score as the original
    reference, then switch the acceptance to the newer record, otherwise intervening
    changes invalidate this request.
    """
    post_action  = ScoreAction.ACCEPT
    action_info  = None
    game_label   = form['game_label']
    bracket      = get_bracket(game_label)
    player_num   = typecast(form['posted_by_num'])
    team_idx     = typecast(form['team_idx'])
    team1_pts    = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts    = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])
    score_pushed = None

    if ref_score:
        # implicit acceptance of a submit or correct action (where scores agree)
        ref_score_id = ref_score.id
    else:
        ref_score_id = typecast(form['ref_score_id'])
        ref_score = PostScore.fetch_by_id(ref_score_id)
        if not ref_score:
            abort(400, f"invalid ref_score_id '{ref_score_id}'")
    assert same_score((team1_pts, team2_pts), ref_score)

    # check for intervening corrections
    latest = PostScore.get_last(game_label, include_accept=True)
    if latest != ref_score:
        assert latest.created_at > ref_score.created_at
        if latest.post_action == ScoreAction.ACCEPT:
            score_pushed = True
            post_action += ScoreAction.DISCARD
            action_info = "Intervening acceptance"
            flash(f"Discarding acceptance due to {lc_first(action_info)} "
                  f"({post_info(latest, team_idx)})")
        elif same_score(latest, ref_score):
            if latest.team_idx != team_idx:
                # same score correction from opponent
                ref_score = latest
                action_info = f"Changing ref_score from id {ref_score_id} to id {latest.id}"
            else:
                # same score correction from partner
                post_action += ScoreAction.DISCARD
                action_info = "Intervening correction from partner"
                flash(f"Discarding acceptance due to {lc_first(action_info)} "
                      f"({post_info(latest, team_idx)})")
        else:
            # changed score correction (from either partner or opponent)
            post_action += ScoreAction.DISCARD
            action_info = "Intervening correction"
            flash(f"Discarding acceptance due to {lc_first(action_info)} "
                  f"({post_info(latest, team_idx)})")

    do_push = (post_action == ScoreAction.ACCEPT)
    info = {
        'bracket'      : bracket,
        'game_label'   : game_label,
        'post_action'  : post_action,
        'action_info'  : action_info,
        'team1_pts'    : team1_pts,
        'team2_pts'    : team2_pts,
        'posted_by_num': player_num,
        'team_idx'     : team_idx,
        'ref_score'    : ref_score,
        'do_push'      : do_push
    }
    score = PostScore.create(**info)
    if not do_push:
        if score_pushed:
            return render_game_in_view(game_label)
        return render_view(BRACKET_VIEW[bracket])
    score.push_scores()
    # ATTN: we really need to consolidate this with the same general call sequence used
    # for updates through the admin interface (in data.py)!!!
    update_rankings(bracket)
    update_tourn_stage(bracket)
    # be a little fancy here and highlight the accepted game
    return render_game_in_view(game_label)

def correct_score(form: dict, ref_score: PostScore = None) -> str:
    """Correct a game score, superceding all previous submitted (or corrected) scores.  As
    with "submit", this score will need to be accepted in order to be pushed.  This can be
    called on behalf of either team.

    If the specified score is identical to the reference entry, this correction will be
    treated as an acceptance if coming from an opponent, or will be ignored if coming from
    a partner.
    """
    post_action  = ScoreAction.CORRECT
    action_info  = None
    game_label   = form['game_label']
    bracket      = get_bracket(game_label)
    player_num   = typecast(form['posted_by_num'])
    team_idx     = typecast(form['team_idx'])
    team1_pts    = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts    = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])
    score_pushed = None

    if ref_score:
        # implicit acceptance of a submit action (where scores agree)
        ref_score_id = ref_score.id
    else:
        ref_score_id = typecast(form['ref_score_id'])
        ref_score = PostScore.fetch_by_id(ref_score_id)
        if not ref_score:
            abort(400, f"invalid ref_score_id '{ref_score_id}'")
    # these should be enforced by the UI (note, repetition here in the case of redirect
    # from a submit action--might as well leave it as an integrity check, in case things
    # get moved around at some point)
    assert max(team1_pts, team2_pts) == GAME_PTS
    assert (team1_pts, team2_pts) != (GAME_PTS, GAME_PTS)

    # check for intervening corrections
    latest = PostScore.get_last(game_label, include_accept=True)
    if latest != ref_score:
        assert latest.created_at > ref_score.created_at
        if latest.post_action == ScoreAction.ACCEPT:
            score_pushed = True
            post_action += ScoreAction.DISCARD
            action_info = "Intervening acceptance"
            flash(f"Discarding update due to {lc_first(action_info)} "
                  f"({post_info(latest, team_idx)})")
        # NOTE that we are always discarding this action if there is an intervening
        # correction (regardless of actor and score), since the logic for implicit
        # acceptance could be messy and/or counterintuitive
        elif same_score(latest, ref_score):
            # REVISIT: we should be able to implicitly accept if updates are from opposing
            # teams!!!
            post_action += ScoreAction.DISCARD
            action_info = "Intervening correction (score unchanged)"
            flash(f"Discarding update due to {lc_first(action_info)} "
                  f"({post_info(latest, team_idx)})")
        else:
            post_action += ScoreAction.DISCARD
            action_info = "Intervening correction"
            flash(f"Discarding update due to {lc_first(action_info)} "
                  f"({post_info(latest, team_idx)})")
    elif same_score((team1_pts, team2_pts), ref_score):
        # NOTE: we used to treat an unchanged score correction to an opponent score as an
        # implicit acceptance, but now we always ignore this action (more intuitive)
        post_action += ScoreAction.IGNORE
        action_info = "Unchanged score correction"
        flash(f"Ignoring {lc_first(action_info)}")

    info = {
        'bracket'      : bracket,
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
    if score_pushed:
        return render_game_in_view(game_label)
    return render_view(BRACKET_VIEW[bracket])

def pick_partner(form: dict) -> str:
    """Submit the specified partner pick.
    """
    player_num = typecast(form['player_num'])
    partner_num = typecast(form['partner_num'])

    # note that we are making sure the cached player map gets this update
    pl_map = Player.get_player_map()
    player = pl_map[player_num]
    partner = pl_map[partner_num]
    player.pick_partners(partner)
    player.save()
    # REVISIT: we should try and incorporate this into update_tourn_stage (would have to
    # rethink the interface for that, though)!!!
    if PartnerPick.current_round() == -1:
        TournInfo.mark_stage_complete(TournStage.PARTNER_PICK)
    return render_view(VIEW_PARTNERS)

#############
# renderers #
#############

# "phase" is a high-level pseudo-stage used to control the display
PHASE_COMMON      = None  # dummy value for common tournament info
PHASE_REGISTER    = "Registration"
PHASE_SEEDING     = "Seeding"
PHASE_PARTNERS    = "Partner Picks"
PHASE_ROUND_ROBIN = "Round Robin"
PHASE_SEMIFINALS  = "Semifinals"
PHASE_FINALS      = "Finals"

VIEW_PHASE = {
    VIEW_INDEX      : None,
    VIEW_REGISTER   : PHASE_REGISTER,
    VIEW_SEEDING    : PHASE_SEEDING,
    VIEW_PARTNERS   : PHASE_PARTNERS,
    VIEW_ROUND_ROBIN: PHASE_ROUND_ROBIN,
    VIEW_SEMIFINALS : PHASE_SEMIFINALS,
    VIEW_FINALS     : PHASE_FINALS
}

VIEW_MENU = [
    #(VIEW_INDEX,       "<i>(current stage)</i>"),
    (VIEW_REGISTER,    PHASE_REGISTER),
    (VIEW_SEEDING,     PHASE_SEEDING),
    (VIEW_PARTNERS,    PHASE_PARTNERS),
    (VIEW_ROUND_ROBIN, PHASE_ROUND_ROBIN),
    (VIEW_SEMIFINALS,  PHASE_SEMIFINALS),
    (VIEW_FINALS,      PHASE_FINALS)
]

def view_menu(player: Player) -> dict[str, str]:
    """Return dict of view name (URL) to menu label for the specified player.  Note that
    menu label is the same as the associated phase name.
    """
    team = player.team  # may be `None` if teams not yet picked
    if not team:
        return VIEW_MENU[:-2]
    elif not team.playoff_team:
        return VIEW_MENU[:-2]
    elif not team.finals_team:
        return VIEW_MENU[:-1]
    return VIEW_MENU

VIEW_RESOURCES = {
    VIEW_SEEDING    : [('/chart/sd_bracket',   "Seeding Bracket"),
                       ('/chart/sd_scores',    "Seeding Scores")],
    VIEW_ROUND_ROBIN: [('/chart/rr_brackets',  "Round Robin Brackets"),
                       ('/chart/rr_scores',    "Round Robin Scores"),
                       ('/report/tie_breaker', "Tie-Breaker Report")]
}

class UserInfo(NamedTuple):
    """Readonly user info/stats field
    """
    name   : str  # also used as the element id
    cls    : str  # CSS class for info data span
    label  : str
    min_stg: TournStage  # refers to stage_compl

INFO_FIELDS = {
    PHASE_COMMON: [
        UserInfo("full_name",  "wide", "Player", TournStage.PLAYER_ROSTER),
        UserInfo("tourn",      "wide", "Tournament", TournStage.TOURN_CREATE),
    ],
    PHASE_REGISTER: [
        UserInfo("status",     "",     "Status (stage)", TournStage.TOURN_CREATE),
        UserInfo("reg_status", "",     "Status (you)", TournStage.TOURN_CREATE)
    ],
    PHASE_SEEDING: [
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("plyr_name",  "med",  "Name",   TournStage.PLAYER_NUMS),
        UserInfo("plyr_num",   "",     "Num",    TournStage.PLAYER_NUMS),
        UserInfo("win_rec_sd", "",     "W-L",    TournStage.SEED_BRACKET),
        UserInfo("pts_pct_sd", "",     "Pts %",  TournStage.SEED_BRACKET),
        UserInfo("seed_rank",  "",     "Rank",   TournStage.SEED_BRACKET)
    ],
    PHASE_PARTNERS: [
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("cur_pick",   "",     "Cur Pick (rank)", TournStage.SEED_TABULATE),
        UserInfo("plyr_name",  "med",  "Name",   TournStage.SEED_TABULATE),
        UserInfo("seed_rank",  "",     "Pick Order", TournStage.SEED_TABULATE)
    ],
    PHASE_ROUND_ROBIN: [
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("team_name",  "wide", "Team",   TournStage.TOURN_TEAMS),
        UserInfo("div_num",    "",     "Div",    TournStage.TOURN_TEAMS),
        UserInfo("div_seed",   "",     "Seed",   TournStage.TOURN_TEAMS),
        UserInfo("win_rec_rr", "",     "W-L",    TournStage.TOURN_BRACKET),
        UserInfo("pts_pct_rr", "",     "Pts %",  TournStage.TOURN_BRACKET),
        UserInfo("div_rank",   "",     "Div Rank", TournStage.TOURN_BRACKET),
        UserInfo("tourn_rank", "",     "Team Rank", TournStage.TOURN_BRACKET)
    ],
    PHASE_SEMIFINALS: [
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("team_name",  "wide", "Team",   TournStage.TOURN_TEAMS),
        UserInfo("tourn_rank", "",     "Rank",   TournStage.TOURN_BRACKET),
        UserInfo("win_rec_pl", "",     "W-L",    TournStage.SEMIS_BRACKET),
        UserInfo("pts_pct_pl", "",     "Pts %",  TournStage.SEMIS_BRACKET),
        UserInfo("playoff_rank", "",   "Semis Rank", TournStage.SEMIS_BRACKET)
    ],
    PHASE_FINALS: [
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("team_name",  "wide", "Team",   TournStage.TOURN_TEAMS),
        UserInfo("tourn_rank", "",     "Rank",   TournStage.TOURN_BRACKET),
        UserInfo("win_rec_pl", "",     "W-L",    TournStage.FINALS_BRACKET),
        UserInfo("pts_pct_pl", "",     "Pts %",  TournStage.FINALS_BRACKET),
        UserInfo("playoff_rank", "",   "Finals Rank", TournStage.FINALS_BRACKET)
    ]
}

def render_view(view: str) -> str:
    """Render the specified view using redirect (called from POST action handlers).
    """
    return redirect(MOBILE_URL_PFX + '/' + view)

def render_game_in_view(label: str) -> str:
    """Return the url for jumping to the specified game in its stage view.  We do a tricky
    thing here and pass the game label to the view using a flashed message (instead of as
    an ugly query string).
    """
    bracket = get_bracket(label)
    view = BRACKET_VIEW[bracket]
    flash(f"cur_game={label}")
    return render_view(view)

def render_mobile(context: dict, view: str) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    tourn       = TournInfo.get(requery=True)
    player      = current_user
    team        = current_user.team
    view_phase  = VIEW_PHASE[view]
    cur_game    = None
    team_idx    = None
    cur_pick    = None
    win_rec_sd  = None
    pts_pct_sd  = None
    win_rec_rr  = None
    pts_pct_rr  = None
    ref_score   = None
    opp_idx     = None
    team_tag    = None
    team_pts    = None
    opp_tag     = None
    opp_pts     = None
    nums_avail  = None
    stage_games = None
    leaderboard = None
    partner_picks = None
    picks_avail = None

    if view_phase in (PHASE_SEMIFINALS, PHASE_FINALS):
        assert team and team.playoff_team
        if view_phase == PHASE_FINALS:
            assert team.finals_team
        cur_game   = team.current_playoff_game
        team_idx   = cur_game.team_idx(team) if cur_game else None
        win_rec_pl = fmt_rec(team.playoff_wins, team.playoff_losses)
        pts_pct_pl = fmt_pct(team.playoff_pts_pct)
    elif view_phase == PHASE_ROUND_ROBIN:
        if team:
            cur_game   = team.current_game
            team_idx   = cur_game.team_idx(team) if cur_game else None
            win_rec_rr = fmt_rec(team.tourn_wins, team.tourn_losses)
            pts_pct_rr = fmt_pct(team.tourn_pts_pct)
    elif view_phase == PHASE_PARTNERS:
        cur_pick   = PartnerPick.current_pick()
    elif view_phase == PHASE_SEEDING:
        cur_game   = player.current_game
        team_idx   = cur_game.team_idx(player) if cur_game else None
        win_rec_sd = fmt_rec(player.seed_wins, player.seed_losses)
        pts_pct_sd = fmt_pct(player.seed_pts_pct)
    else:
        assert view_phase == PHASE_REGISTER

    if cur_game:
        if context.get('cur_game'):
            # if `cur_game` was passed in to us, it takes precendence (e.g. highlight game
            # for accepted score)
            cur_game = context.get('cur_game')
            assert cur_game.winner
            team_idx = cur_game.team_idx(team if team else player)
            ref_score = PostScore.get_last(cur_game.label, include_accept=True)
        assert team_idx in (0, 1)
        opp_idx  = team_idx ^ 0x01
        map_pts  = lambda x, i: x.team1_pts if i == 0 else x.team2_pts
        team_tag = cur_game.team_tags[team_idx]
        team_pts = map_pts(cur_game, team_idx)
        opp_tag  = cur_game.team_tags[opp_idx]
        opp_pts  = map_pts(cur_game, opp_idx)
        if not context.get('cur_game'):
            assert not cur_game.winner
            ref_score = PostScore.get_last(cur_game.label)
            if ref_score:
                team_pts = map_pts(ref_score, team_idx)
                opp_pts = map_pts(ref_score, opp_idx)

    info_data = {
        PHASE_COMMON: [
            player.full_name,
            tourn.name
        ]
    }
    if view_phase == PHASE_REGISTER:
        info_data[PHASE_REGISTER] = [
            PlayerRegister.phase_status(),
            PlayerRegister.reg_status(player)
        ]
    elif view_phase == PHASE_SEEDING:
        info_data[PHASE_SEEDING] = [
            SeedGame.phase_status(),
            player.name,
            player.player_num,
            win_rec_sd,
            pts_pct_sd,
            player.player_rank
        ]
    elif view_phase == PHASE_PARTNERS:
        info_data[PHASE_PARTNERS] = [
            PartnerPick.phase_status(),
            cur_pick.player_rank if cur_pick else None,
            player.name,
            player.player_rank
        ]
    elif view_phase == PHASE_ROUND_ROBIN:
        info_data[PHASE_ROUND_ROBIN] = [
            TournGame.phase_status()
        ]
        if team:
            info_data[PHASE_ROUND_ROBIN] += [
                team.team_name,
                team.div_num,
                team.div_seed,
                win_rec_rr,
                pts_pct_rr,
                team.div_rank,
                team.tourn_rank
            ]
        else:
            info_data[PHASE_ROUND_ROBIN] += [None] * 7
    elif view_phase == PHASE_SEMIFINALS:
        info_data[PHASE_SEMIFINALS] = [
            PlayoffGame.phase_status(Bracket.SEMIS),
            team.team_name,
            team.tourn_rank,
            win_rec_pl,
            pts_pct_pl,
            team.playoff_rank
        ]
    elif view_phase == PHASE_FINALS:
        info_data[PHASE_FINALS] = [
            PlayoffGame.phase_status(Bracket.FINALS),
            team.team_name,
            team.tourn_rank,
            win_rec_pl,
            pts_pct_pl,
            team.playoff_rank
        ]
    for phase, data in info_data.items():
        assert len(data) == len(INFO_FIELDS[phase])

    if view_phase == PHASE_REGISTER:
        # REVISIT: note that we are currently also using this as an indicator of whether
        # registration is still active, or if the player info has been locked down!!!
        if tourn.stage_compl < TournStage.PLAYER_NUMS:
            nums_avail = Player.nums_avail(player)
        else:
            nums_avail = None
    if view_phase == PHASE_SEEDING:
        stage_games = player.get_games(all_games=True)
        leaderboard = get_leaderboard(Bracket.SEED)
    elif view_phase == PHASE_PARTNERS:
        partner_picks = PartnerPick.get_picks(all_picks=True)
        picks_avail = PartnerPick.avail_picks()
    elif view_phase == PHASE_ROUND_ROBIN:
        stage_games = team.get_games(all_games=True) if team else None
        leaderboard = get_leaderboard(Bracket.TOURN, team.div_num) if team else None
    elif view_phase == PHASE_SEMIFINALS:
        stage_games = team.get_playoff_games(Bracket.SEMIS, all_games=True)
        leaderboard = get_leaderboard(Bracket.SEMIS)
    elif view_phase == PHASE_FINALS:
        stage_games = team.get_playoff_games(Bracket.FINALS, all_games=True)
        leaderboard = get_leaderboard(Bracket.FINALS)

    # FIX: for now we're not worried about too many context items (since we are trying to
    # develop clear semantics for the display), but this is inelegant and getting bloated
    # and redundant, so we really need to refactor into something with better structure!!!
    base_ctx = {
        'title'        : MOBILE_TITLE,
        'view_menu'    : view_menu(player),
        'view_phase'   : view_phase,
        'view'         : view,
        'index'        : VIEW_INDEX,
        'register'     : VIEW_REGISTER,
        'seeding'      : VIEW_SEEDING,
        'partners'     : VIEW_PARTNERS,
        'round_robin'  : VIEW_ROUND_ROBIN,
        'semifinals'   : VIEW_SEMIFINALS,
        'finals'       : VIEW_FINALS,
        'tourn'        : tourn,
        'user'         : current_user,
        'team'         : team,
        'team_idx'     : team_idx,
        'info_flds'    : INFO_FIELDS,
        'info_data'    : info_data,
        'cur_game'     : cur_game,
        'cur_pick'     : cur_pick,
        'team_tag'     : team_tag,
        'team_pts'     : team_pts,
        'opp_tag'      : opp_tag,
        'opp_pts'      : opp_pts,
        'ref_score'    : ref_score,
        'ref_score_id' : ref_score.id if ref_score else None,
        'nums_avail'   : nums_avail,
        'stage_games'  : stage_games,
        'leaderboard'  : leaderboard,
        'partner_picks': partner_picks,
        'picks_avail'  : picks_avail,
        'fmt_matchup'  : fmt_matchup,
        'resources'    : VIEW_RESOURCES.get(view),
        'err_msg'      : None
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
