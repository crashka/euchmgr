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

from core import ImplementationError
from schema import (GAME_PTS, BRACKET_SEED, BRACKET_TOURN, TournStage, TournInfo, Player,
                    SeedGame, Team, TournGame, PostScore, SCORE_SUBMIT, SCORE_ACCEPT,
                    SCORE_CORRECT, SCORE_IGNORE, SCORE_DISCARD)
from euchmgr import PFX_SEED, PFX_TOURN, compute_player_ranks, compute_team_ranks

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

# some type aliases (local scope for now, but perhaps adopt more broadly later, especially
# if/when we abstract out the schema)
BracketGame = SeedGame | TournGame
PartnerPick = Player
StageMgr    = BracketGame | PartnerPick

def stage_status(stage_mgr: StageMgr) -> str:
    """Return current stage status (i.e. round info)
    """
    cur_round = stage_mgr.current_round()
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

def get_game_by_label(label: str) -> SeedGame | TournGame:
    """Use a little ORM knowledge to fetch from the appropriate table--LATER: can put this
    in the right place (or refactor the whole bracket-game thing)!!!
    """
    game_cls = SeedGame if get_bracket(label) == BRACKET_SEED else TournGame
    query = (game_cls
             .select()
             .where(game_cls.label == label))
    return query.get_or_none()

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

# format a record string (e.g. given wins/losses or pts_for/pts_against)
fmt_rec = lambda x, y: f"{x}-{y}"

def get_leaderboard(bracket: str, div: int = None) -> list[tuple[str, str, str, str]]:
    """Return tuples of (player/team, W-L, PF-PA, rank) ordered by rank.  `div` must be
    specified for BRACKET_TOURN.
    """
    if bracket == BRACKET_SEED:
        pl_list = list(Player.iter_players(by_rank=True))
        return [(pl.player_tag, fmt_rec(pl.seed_wins, pl.seed_losses),
                 fmt_rec(pl.seed_pts_for, pl.seed_pts_against), pl.player_rank or "")
                for pl in pl_list]
    else:
        assert bracket == BRACKET_TOURN
        assert div
        tm_list = list(Team.iter_teams(div=div, by_rank=True))
        return [(tm.team_tag, fmt_rec(tm.tourn_wins, tm.tourn_losses),
                 fmt_rec(tm.tourn_pts_for, tm.tourn_pts_against), tm.div_rank or "")
                for tm in tm_list]

def update_rankings(bracket: str) -> bool:
    """Update rankings for the specified bracket.  The return value indicates whether this
    call synchronous performed the update (otherwise, the execution is assumed deferred).

    REVISIT: this is kind of code-heavy, so we may not want to do it every time a score is
    posted--if we find updates tripping over each other, we can create a global timestamp
    to ensure that updates are appropriate spaced!!!

    """
    if bracket == BRACKET_SEED:
        compute_player_ranks()
    else:
        assert bracket == BRACKET_TOURN
        compute_team_ranks()
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
    BRACKET_SEED : VIEW_SEEDING,
    BRACKET_TOURN: VIEW_ROUND_ROBIN
}

STAGE_VIEW = [
    (TournStage.TOURN_TEAMS,  VIEW_ROUND_ROBIN),
    (TournStage.SEED_RANKS,   VIEW_PARTNERS),
    (TournStage.SEED_BRACKET, VIEW_SEEDING),
    (TournStage.PLAYER_NUMS,  VIEW_REGISTER)
]

def dflt_view(tourn: TournInfo) -> str:
    """Return most relevant view for the current stage of the tournament
    """
    if tourn.stage_start is None:
        return None
    for stage, view in STAGE_VIEW:
        if tourn.stage_start >= stage:
            return view
    return None

@mobile.get("/")
def index() -> str:
    """Render mobile app if logged in
    """
    if not current_user.is_authenticated:
        flash("Please reauthenticate in order to access the app")
        return redirect('/login')

    tourn = TournInfo.get()
    view = dflt_view(tourn)
    if view:
        # REVISIT: we should figure out if we need to forward these on--they may stayed
        # queued through the redirect!!!
        msgs = get_flashed_messages()
        for msgs in get_flashed_messages():
            flash(msgs)
        return render_view(view)

    context = {}
    msgs = get_flashed_messages()
    context['err_msg'] = "<br>".join(msgs)
    return render_mobile(context)

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
        return redirect('/login')
    view = request.path.split('/')[-1]

    context = {}
    game_label = None
    msgs = get_flashed_messages()
    # see if any secret parameters have been transmitted to us--NOTE: currently only one
    # secret parameter is expected, so we need to be careful that no additional messages
    # are flashed, otherwise the "secret" parameter will be rendered in the app as an
    # error messsage, lol
    if len(msgs) == 1 and msgs[0].find('=') > 0:
        key, val = msgs[0].split('=', 1)
        if key == 'cur_game':
            assert not request.args.get('cur_game')
            game_label = val
        else:
            raise ImplementationError(f"unexpected secret key '{key}' (value '{val}')")
    else:
        context['err_msg'] = "<br>".join(msgs)

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
    assert False, "not yet implemented"

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
    bracket     = get_bracket(game_label)
    player_num  = typecast(form['posted_by_num'])
    team_idx    = typecast(form['team_idx'])
    team1_pts   = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts   = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

    ref_score_id = typecast(form['ref_score_id'])
    if ref_score_id is not None:
        abort(400, f"ref_score_id ({ref_score_id}) should not be set")
    # these should be enforced by the UI
    assert max(team1_pts, team2_pts) == GAME_PTS
    assert (team1_pts, team2_pts) != (GAME_PTS, GAME_PTS)

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
    return render_view(BRACKET_VIEW[bracket])

def accept_score(form: dict) -> str:
    """Accept a game score posted by an opponent.

    If an intervening correction from an opponent has the same score as the original
    reference, then switch the acceptance to the newer record, otherwise intervening
    changes invalidate this request.
    """
    post_action = SCORE_ACCEPT
    action_info = None
    game_label  = form['game_label']
    bracket     = get_bracket(game_label)
    player_num  = typecast(form['posted_by_num'])
    team_idx    = typecast(form['team_idx'])
    team1_pts   = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts   = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

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
        'bracket'      : bracket,
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
            update_rankings(bracket)
        except RuntimeError as e:
            flash(str(e))
            return render_view(VIEW_PARTNERS)
    return render_game_in_view(game_label)

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
    game_label  = form['game_label']
    bracket     = get_bracket(game_label)
    player_num  = typecast(form['posted_by_num'])
    team_idx    = typecast(form['team_idx'])
    team1_pts   = typecast(form['team_pts'] if team_idx == 0 else form['opp_pts'])
    team2_pts   = typecast(form['team_pts'] if team_idx == 1 else form['opp_pts'])

    ref_score_id = typecast(form['ref_score_id'])
    ref_score = PostScore.get_or_none(ref_score_id)
    if not ref_score:
        abort(400, f"invalid ref_score_id {ref_score_id}")
    # these should be enforced by the UI
    assert max(team1_pts, team2_pts) == GAME_PTS
    assert (team1_pts, team2_pts) != (GAME_PTS, GAME_PTS)

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
    return render_view(BRACKET_VIEW[bracket])

def pick_partner(form: dict) -> str:
    """Submit the specified partner pick.
    """
    player_num = typecast(form['player_num'])
    partner_num = typecast(form['partner_num'])

    # note that we are making sure the cached player map gets this update
    pl_map = Player.get_player_map(requery=True)
    player = pl_map[player_num]
    partner = pl_map[partner_num]
    player.pick_partners(partner)
    player.save()
    return render_view(VIEW_PARTNERS)

#############
# renderers #
#############

# "phase" is a high-level pseudo-stage used to control the display
PHASE_COMMON      = None  # dummy value for common tournament info
PHASE_REGISTER    = "Register"
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

VIEW_MENU = {
    VIEW_INDEX      : "<i>(current)</i>",
    VIEW_REGISTER   : "Register",
    VIEW_SEEDING    : "Seeding",
    VIEW_PARTNERS   : "Partner Picks",
    VIEW_ROUND_ROBIN: "Round Robin"
}

VIEW_RESOURCES = {
    VIEW_SEEDING    : [('/chart/sd_bracket',    "Seeding Bracket"),
                       ('/chart/sd_scores',     "Seeding Scores")],
    VIEW_ROUND_ROBIN: [('/chart/rr_brackets',   "Round Robin Brackets"),
                       ('/chart/rr_scores',     "Round Robin Scores"),
                       ('/report/rr_tb_report', "Tie-Breaker Report")]
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
    PHASE_SEEDING: [
        UserInfo("stage",      "med",  "Stage",  TournStage.TOURN_CREATE),
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("plyr_name",  "med",  "Name",   TournStage.PLAYER_NUMS),
        UserInfo("plyr_num",   "",     "Num",    TournStage.PLAYER_NUMS),
        UserInfo("win_rec_sd", "",     "W-L",    TournStage.SEED_BRACKET),
        UserInfo("pts_rec_sd", "",     "PF-PA",  TournStage.SEED_BRACKET),
        UserInfo("seed_rank",  "",     "Rank",   TournStage.SEED_BRACKET)
    ],
    PHASE_PARTNERS: [
        UserInfo("stage",      "med",  "Stage",  TournStage.TOURN_CREATE),
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("cur_pick",   "",     "Cur Pick (rank)", TournStage.SEED_TABULATE),
        UserInfo("plyr_name",  "med",  "Name",   TournStage.SEED_TABULATE),
        UserInfo("seed_rank",  "",     "Rank",   TournStage.SEED_TABULATE)
    ],
    PHASE_ROUND_ROBIN: [
        UserInfo("stage",      "med",  "Stage",  TournStage.TOURN_CREATE),
        UserInfo("status",     "",     "Status", TournStage.TOURN_CREATE),
        UserInfo("team_name",  "wide", "Team",   TournStage.TOURN_TEAMS),
        UserInfo("div_num",    "",     "Div",    TournStage.TOURN_TEAMS),
        UserInfo("div_seed",   "",     "Seed",   TournStage.TOURN_TEAMS),
        UserInfo("win_rec_rr", "",     "W-L",    TournStage.TOURN_BRACKET),
        UserInfo("pts_rec_rr", "",     "PF-PA",  TournStage.TOURN_BRACKET),
        UserInfo("div_rank",   "",     "Rank",   TournStage.TOURN_BRACKET)
    ]
}

def render_view(view: str) -> str:
    """Render the specified view using redirect (called from POST action handlers).
    """
    return redirect('/mobile/' + view)

def render_game_in_view(label: str) -> str:
    """Return the url for jumping to the specified game in its stage view.  We do a tricky
    thing here and pass the game label to the view using a flashed message (instead of as
    an ugly query string).
    """
    bracket = get_bracket(label)
    view = BRACKET_VIEW[bracket]
    flash(f"cur_game={label}")
    return render_view(view)

def render_mobile(context: dict, view: str = VIEW_INDEX) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    tourn       = TournInfo.get(requery=True)
    player      = current_user
    team        = current_user.team
    cur_phase   = None
    cur_game    = None
    team_idx    = None
    cur_pick    = None
    win_rec_sd  = None
    pts_rec_sd  = None
    win_rec_rr  = None
    pts_rec_rr  = None
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

    if tourn.stage_start >= TournStage.TOURN_BRACKET:
        assert team
        cur_phase  = PHASE_ROUND_ROBIN
        cur_game   = team.current_game
        team_idx   = cur_game.team_idx(team) if cur_game else None
        win_rec_sd = fmt_rec(player.seed_wins, player.seed_losses)
        pts_rec_sd = fmt_rec(player.seed_pts_for, player.seed_pts_against)
        win_rec_rr = fmt_rec(team.tourn_wins, team.tourn_losses)
        pts_rec_rr = fmt_rec(team.tourn_pts_for, team.tourn_pts_against)
    elif tourn.stage_start >= TournStage.PARTNER_PICK:
        cur_phase  = PHASE_PARTNERS
        cur_pick   = PartnerPick.current_pick()
        win_rec_sd = fmt_rec(player.seed_wins, player.seed_losses)
        pts_rec_sd = fmt_rec(player.seed_pts_for, player.seed_pts_against)
    elif tourn.stage_start >= TournStage.SEED_BRACKET:
        cur_phase  = PHASE_SEEDING
        cur_game   = player.current_game
        team_idx   = cur_game.team_idx(player) if cur_game else None
        win_rec_sd = fmt_rec(player.seed_wins, player.seed_losses)
        pts_rec_sd = fmt_rec(player.seed_pts_for, player.seed_pts_against)
    elif tourn.stage_start >= TournStage.PLAYER_NUMS:
        cur_phase  = PHASE_REGISTER

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

    display_phase = VIEW_PHASE[view] or cur_phase
    info_data = {
        PHASE_COMMON: [
            player.full_name,
            tourn.name
        ]
    }
    if display_phase == PHASE_SEEDING:
        info_data[PHASE_SEEDING] = [
            PHASE_SEEDING,
            stage_status(SeedGame),
            player.nick_name,
            player.player_num,
            win_rec_sd,
            pts_rec_sd,
            player.player_rank
        ]
    if display_phase == PHASE_PARTNERS:
        info_data[PHASE_PARTNERS] = [
            PHASE_PARTNERS,
            stage_status(PartnerPick),
            cur_pick.player_rank if cur_pick else None,
            player.nick_name,
            player.player_rank
        ]
    elif display_phase == PHASE_ROUND_ROBIN:
        info_data[PHASE_ROUND_ROBIN] = [
            PHASE_ROUND_ROBIN,
            stage_status(TournGame)
        ]
        if team:
            info_data[PHASE_ROUND_ROBIN] += [
                team.team_name,
                team.div_num,
                team.div_seed,
                win_rec_rr,
                pts_rec_rr,
                team.div_rank
            ]
        else:
            info_data[PHASE_ROUND_ROBIN] += [None] * 6
    for phase, data in info_data.items():
        assert len(data) == len(INFO_FIELDS[phase])

    if VIEW_PHASE[view] == PHASE_REGISTER:
        # FIX: need to replace this will currently unassigned numbers!!!
        # REVISIT: note that we are currently also using this as an indicator of whether
        # registration is still active, or if the player info has been locked down!!!
        if tourn.stage_compl < TournStage.PLAYER_NUMS:
            nums_avail = range(1, tourn.players + 1)
        else:
            nums_avail = None
    if VIEW_PHASE[view] == PHASE_SEEDING:
        stage_games = player.get_games(all_games=True)
        leaderboard = get_leaderboard(BRACKET_SEED)
    elif VIEW_PHASE[view] == PHASE_ROUND_ROBIN:
        stage_games = team.get_games(all_games=True) if team else None
        leaderboard = get_leaderboard(BRACKET_TOURN, team.div_num) if team else None
    elif VIEW_PHASE[view] == PHASE_PARTNERS:
        partner_picks = PartnerPick.get_picks(all_picks=True)
        picks_avail = PartnerPick.available_partners()

    # FIX: for now we're not worried about too many context items (since we are trying to
    # develop clear semantics for the display), but this is inelegant and getting bloated
    # and redundant, so we really need to refactor into something with better structure!!!
    base_ctx = {
        'title'        : MOBILE_TITLE,
        'view_menu'    : VIEW_MENU,
        'view'         : view,
        'index'        : VIEW_INDEX,
        'register'     : VIEW_REGISTER,
        'seeding'      : VIEW_SEEDING,
        'partners'     : VIEW_PARTNERS,
        'round_robin'  : VIEW_ROUND_ROBIN,
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
        'fmt_rec'      : fmt_rec,
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
