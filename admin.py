# -*- coding: utf-8 -*-

"""Blueprint for the admin interface
"""

from typing import NamedTuple
from enum import StrEnum
from functools import wraps
from collections.abc import Callable
from glob import glob
import os.path
import re

from ckautils import typecast
from peewee import OperationalError
from flask import Blueprint, g, request, session, abort, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from core import DATA_DIR, UPLOAD_DIR, config, profile, log, ImplementationError
from security import current_user, admin_required, DUMMY_PW_STR
from database import (DB_FILETYPE, db_atomic, db_init, db_name, db_reset, db_is_initialized,
                      db_prepare, db_checkpoint)
from schema import (clear_schema_cache, Bracket, TournStage, TOURN_INIT, ALL_STAGES,
                    PRELIM_STAGES, ACTIVE_STAGES, TournInfo, TournEvent, TournLog,
                    Player, SeedGame, TournGame, PlayoffGame)
from euchmgr import (tourn_create, upload_roster, generate_player_nums, build_seed_bracket,
                     fake_seed_games, validate_seed_round, compute_player_ranks,
                     prepick_champ_partners, fake_pick_partners, build_tourn_teams,
                     compute_team_seeds, build_tourn_bracket, fake_tourn_games,
                     validate_tourn, compute_team_ranks, build_playoff_bracket,
                     fake_playoff_games, validate_playoffs, compute_playoff_ranks,
                     compute_final_ranks)
from ui_common import (process_flashes, msg_join, cap_first, render_response, redirect,
                       render_error, api_succ, api_error)
from data import (Layout, pl_layout, sg_layout, pt_layout, tm_layout, tg_layout, ff_layout,
                  pg_layout)
from dash import clear_dash_storage

################
# module stuff #
################

cfg = config.config('admin', profile)

CHKPT_DB = cfg['checkpoint_db']

def admin_action(func: Callable):
    """Decorator for admin actions, to record tourn_log entries, as well as perform
    database checkpoints (either before or after action execution, depending on the
    configuration).  Note that checkpoint "tag" (used for restoration) will be either
    "stage-<num>-activ" (for pre-action) or "stage-<num>-compl" (for post-action).
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        action = func.__name__
        # bare bones logging of action (no additional info/context)
        TournLog.add(TournEvent.ADMIN_ACTION, action)

        # whether/when to checkpoint the database (relative to action)
        chkpt_db = CHKPT_DB.get(action, ['never'])
        tourn = TournInfo.get()
        if 'pre' in chkpt_db:
            chkpt_tag = f"stage-{tourn.stage_start}-activ"
            file = db_checkpoint(chkpt_tag)
            log.notice(f"Database checkpoint written to '{file}'")
        ret = func(*args, **kwargs)
        if 'post' in chkpt_db:
            chkpt_tag = f"stage-{tourn.stage_compl}-compl"
            file = db_checkpoint(chkpt_tag)
            log.notice(f"Database checkpoint written to '{file}'")
        return ret
    return wrapper

###################
# blueprint stuff #
###################

admin = Blueprint('admin', __name__)
APP_NAME = "Euchre Manager"
ADMIN_TEMPLATE = "admin.html"
TOURN_TEMPLATE = "tourn.html"

###############
# tourn stuff #
###############

def get_tourns() -> list[str]:
    """Get list of existing tournaments (currently based on existence of database file in
    DATA_DIR--later, we can do something more structured)
    """
    pattern = '*' + DB_FILETYPE
    files = glob(pattern, root_dir=DATA_DIR)
    return sorted(f.removesuffix(DB_FILETYPE) for f in files)

##############
# view stuff #
##############

class View(StrEnum):
    """The string value for view items also represents (if not defines) their relative
    path name.  Note that _absolute_ path names as needed when redirecting from POST
    actions (hence `view_path`, below).
    """
    TOURN       = 'tourn'
    PLAYERS     = 'players'
    SEEDING     = 'seeding'
    PARTNERS    = 'partners'
    TEAMS       = 'teams'
    ROUND_ROBIN = 'round_robin'
    FINAL_FOUR  = 'final_four'
    PLAYOFFS    = 'playoffs'

def view_path(view: str) -> str:
    """Return absolute path for specified view.  Note that the view name itself is the
    endpoint name within the admin blueprint.
    """
    return url_for('admin.' + view)

class ViewInfo(NamedTuple):
    """This is not super-pretty, but we want to make this as data-driven as possible
    """
    name:       str  # display name
    layout:     Layout
    rowid_col:  str  # column name
    tbl_order:  int  # default sort column(s) (column index)
    fixed_cols: int  # for horizontal scrolling (currently disabled)

# only include views using ADMIN_TEMPLATE
VIEW_DEFS = {
    View.PLAYERS: ViewInfo(
        "Players",
        pl_layout,
        "nick_name",
        [0],  # id
        3
    ),
    View.SEEDING: ViewInfo(
        "Seeding",
        sg_layout,
        "label",
        [0],  # id
        3
    ),
    View.PARTNERS: ViewInfo(
        "Partners",
        pt_layout,
        "nick_name",
        [1],  # player_rank_eff
        3
    ),
    View.TEAMS: ViewInfo(
        "Teams",
        tm_layout,
        "team_name",
        [1],  # team_seed
        2
    ),
    View.ROUND_ROBIN: ViewInfo(
        "Round Robin",
        tg_layout,
        "label",
        [0],  # id
        2
    ),
    View.FINAL_FOUR: ViewInfo(
        "Final Four",
        ff_layout,
        "team_name",
        [1],  # tourn_rank_eff
        2
    ),
    View.PLAYOFFS: ViewInfo(
        "Playoffs",
        pg_layout,
        "label",
        [0],  # id
        2
    )
}

def view_menu() -> list[tuple[str, str]]:
    """Return list of tuples representing navigation menu items of the following form:
    (view, label), where "view" string value doubles as its relative path name.
    """
    return [(str(view), info.name) for view, info in VIEW_DEFS.items()]

STAGE_MAPPING = [
    (TournStage.FINALS_RANKS,   View.FINAL_FOUR),
    (TournStage.FINALS_RESULTS, View.PLAYOFFS),
    (TournStage.SEMIS_RANKS,    View.FINAL_FOUR),
    (TournStage.SEMIS_RESULTS,  View.PLAYOFFS),
    (TournStage.TOURN_RANKS,    View.FINAL_FOUR),
    (TournStage.TOURN_RESULTS,  View.ROUND_ROBIN),
    (TournStage.TEAM_SEEDS,     View.TEAMS),
    (TournStage.PARTNER_PICK,   View.PARTNERS),
    (TournStage.SEED_RESULTS,   View.SEEDING),
    (TournStage.PLAYER_NUMS,    View.PLAYERS),
    (TournStage.TOURN_CREATE,   View.TOURN)
]

def active_view(tourn: TournInfo) -> View:
    """Return active view for the current stage of the tournament.
    """
    if tourn.stage_start is None:
        return None
    for stage, view in STAGE_MAPPING:
        if tourn.stage_start >= stage:
            return view
    return None

CUR_ROUND_FUNC = {
    View.SEEDING    : SeedGame.current_round,
    View.PARTNERS   : Player.current_round,
    View.ROUND_ROBIN: TournGame.current_round
}

def activity_complete(view: str) -> bool | None:
    """Return indication that activity for a long-running stage (i.e. card play or partner
    picking) is complete.  For better or for worse, this call has the same return value
    semantics as `PlayoffGame.bracket_complete`:

      - `None`  - stage has not started or view has no long-running stage
      - `False` - stage has started but activity is not complete
      - `True`  - activity for the stage is complete
    """
    if view == View.PLAYOFFS:
        return PlayoffGame.bracket_complete(None)
    if view not in CUR_ROUND_FUNC:
        return None

    # this is a little ugly, due to unfortunate `current_round` semantics
    cur_round = CUR_ROUND_FUNC[view]()
    if cur_round == 0:
        return None
    else:
        return cur_round == -1

# convenience call with clearer semantics
view_active = lambda view: activity_complete(view) == False

##############
# GET routes #
##############

@admin.get("/tourn")
def tourn() -> str:
    """View used to manage tournament information, as well as create new tournaments.
    """
    if not current_user.is_authenticated:
        return redirect(url_for('login_page'))

    if g.mobile:
        return render_error(403, desc="Mobile access unauthorized")

    params, msgs = process_flashes()
    create_new   = params.pop('create_new', False)
    err_msgs     = params.pop('err', [])
    info_msgs    = params.pop('info', []) + msgs
    if params:
        raise ImplementationError(f"unexpected flashed params '{params}'")

    tourn_name = session.get('tourn')
    if tourn_name:
        assert not create_new
        assert db_is_initialized()
        tourn = TournInfo.get()
        assert tourn.name == tourn_name
        # render admin view for existing tournament
        context = {
            'tourn'    : tourn,
            'no_roster': tourn.stage_compl in PRELIM_STAGES,
            'err_msg'  : msg_join(err_msgs) or msg_join(info_msgs),
            'info_msg' : msg_join(info_msgs)
        }
        return render_tourn(context)

    tourn = TournInfo() if create_new else None
    if db_is_initialized():
        # see REVISIT comment for the `index` route (in server.py)
        tourn = TournInfo.get()
        session['tourn'] = tourn.name
        log.info(f"re-setting tourn = '{tourn.name}' in session state")

    context = {
        'tourn'    : tourn,
        'new_tourn': create_new,
        'no_roster': create_new,
        'err_msg'  : msg_join(err_msgs) or msg_join(info_msgs),
        'info_msg' : msg_join(info_msgs)
    }
    return render_tourn(context)

@admin.get("/players", endpoint="players")
@admin.get("/seeding", endpoint="seeding")
@admin.get("/partners", endpoint="partners")
@admin.get("/teams", endpoint="teams")
@admin.get("/round_robin", endpoint="round_robin")
@admin.get("/final_four", endpoint="final_four")
@admin.get("/playoffs", endpoint="playoffs")
def view() -> str:
    """Render the requested view directly.
    """
    if not current_user.is_authenticated:
        return redirect(url_for('login_page'))

    if g.mobile:
        return render_error(403, desc="Mobile access unauthorized")

    view = request.path.split('/')[-1]
    tourn = TournInfo.get()

    params, msgs = process_flashes()
    err_msgs     = params.pop('err', [])
    info_msgs    = params.pop('info', []) + msgs
    if params:
        raise ImplementationError(f"unexpected flashed params '{params}'")

    context = {
        'tourn'   : tourn,
        'view'    : view,
        'err_msg' : msg_join(err_msgs) or msg_join(info_msgs),
        'info_msg': msg_join(info_msgs)
    }
    return render_admin(context)

COMPL_MAP = {
    View.SEEDING    : [TournStage.SEED_RESULTS],
    View.PARTNERS   : [TournStage.PARTNER_PICK],
    View.ROUND_ROBIN: [TournStage.TOURN_RESULTS],
    View.PLAYOFFS   : [TournStage.SEMIS_RESULTS, TournStage.FINALS_RESULTS]
}

@admin.get("/check_compl/<view>")
@admin_action
def check_compl(view: str) -> str:
    """Return stage completion status for the specified view.  Uses API return data (json)
    protocol.  The `complete` data field value carries same semantics as the underlying
    `activity_complete` call.  Mark the tournament stage complete, as appropriate.
    """
    compl = activity_complete(view)
    if compl:
        tourn = TournInfo.get()
        for stage in COMPL_MAP[view]:
            if tourn.stage_start == stage and tourn.stage_compl < stage:
                assert tourn.stage_compl == stage - 1
                tourn.complete_stage(stage)
                break
    return api_succ(data={'complete': compl})

################
# POST actions #
################

VIEW_ACTIONS = {
    View.TOURN: [
        'select_tourn',
        'create_tourn',
        'update_tourn',
        'pause_tourn'
    ],
    View.PLAYERS: [
        'gen_player_nums',
        'gen_seed_bracket',
        'add_player',
        'remove_player',
        'clear_player_nums'
    ],
    View.SEEDING: [
        'fake_seed_results',
        'tabulate_seed_results',
        'clear_seed_results'
    ],
    View.PARTNERS: [
        'fake_partner_picks',
        'comp_team_seeds',
        'clear_partner_picks'
    ],
    View.TEAMS: [
        'gen_tourn_brackets'
    ],
    View.ROUND_ROBIN: [
        'fake_tourn_results',
        'tabulate_tourn_results',
        'clear_tourn_results'
    ],
    View.FINAL_FOUR: [
        'gen_semis_bracket',
        'gen_finals_bracket'
    ],
    View.PLAYOFFS: [
        'fake_semis_results',
        'fake_finals_results',
        'tabulate_semis_results',
        'tabulate_finals_results',
        'clear_playoff_results'
    ]
}

POWER_ACTIONS = [
    'add_player',
    'remove_player',
    'clear_player_nums',
    'clear_seed_results',
    'clear_partner_picks',
    'clear_tourn_results',
    'clear_playoff_results'
]

TEST_ACTIONS = [
    'fake_seed_results',
    'fake_partner_picks',
    'fake_tourn_results',
    'fake_semis_results',
    'fake_finals_results'
]

# key: action function (doubles as button name in views)
# value: tuple(action/button display name, list of stages when valid/callable)
ACTION_INFO = {
    'select_tourn'           : ("[Ceci n'existe pas]",         ALL_STAGES),
    'create_tourn'           : ("Create Tournament",           PRELIM_STAGES),
    'update_tourn'           : ("Update Tournament",           ACTIVE_STAGES),
    'pause_tourn'            : ("Pause Tournament",            ACTIVE_STAGES),
    'gen_player_nums'        : ("Generate Player Nums",        [TournStage.PLAYER_ROSTER]),
    'gen_seed_bracket'       : ("Create Seeding Bracket",      [TournStage.PLAYER_NUMS]),
    'fake_seed_results'      : ("Generate Fake Results",       [TournStage.SEED_BRACKET]),
    'tabulate_seed_results'  : ("Tabulate Results",            [TournStage.SEED_RESULTS]),
    'fake_partner_picks'     : ("Generate Fake Picks",         [TournStage.SEED_RANKS]),
    'comp_team_seeds'        : ("Compute Team Seeds",          [TournStage.PARTNER_PICK]),
    'gen_tourn_brackets'     : ("Create Round Robin Brackets", [TournStage.TEAM_SEEDS]),
    'fake_tourn_results'     : ("Generate Fake Results",       [TournStage.TOURN_BRACKET]),
    'tabulate_tourn_results' : ("Tabulate Results",            [TournStage.TOURN_RESULTS]),
    'gen_semis_bracket'      : ("Create Semis Bracket",        [TournStage.TOURN_RANKS]),
    'fake_semis_results'     : ("Gen Fake Semis Results",      [TournStage.SEMIS_BRACKET]),
    'tabulate_semis_results' : ("Tabulate Semis Results",      [TournStage.SEMIS_RESULTS]),
    'gen_finals_bracket'     : ("Create Finals Bracket",       [TournStage.SEMIS_RANKS]),
    'fake_finals_results'    : ("Gen Fake Finals Results",     [TournStage.FINALS_BRACKET]),
    'tabulate_finals_results': ("Tabulate Finals Results",     [TournStage.FINALS_RESULTS])
}

@admin.post("/tourn/<action>")
@admin.post("/players/<action>")
@admin.post("/seeding/<action>")
@admin.post("/partners/<action>")
@admin.post("/teams/<action>")
@admin.post("/round_robin/<action>")
@admin.post("/final_four/<action>")
@admin.post("/playoffs/<action>")
@admin_required
def view_action(action: str) -> str:
    """Process submitted form, switch on ``action``, which is validated against paths and
    values in ``VIEW_ACTIONS``
    """
    if not current_user.is_authenticated:
        abort(401, "Not authenticated")

    view = request.path.split('/')[-2]
    if view not in VIEW_ACTIONS:
        abort(404, f"Invalid action target '{view}'")
    if 'action' not in request.form:
        abort(400, "Invalid request, no action specified")
    form_action = request.form['action']
    if form_action != action:
        abort(400, f"Invalid request, mismatched action '{form_action}'")
    if action not in VIEW_ACTIONS[view]:
        abort(400, f"Invalid action '{action}' for target '{view}'")

    assert action in ACTION_INFO
    valid_stages = ACTION_INFO[action][1]
    if db_is_initialized():
        tourn = TournInfo.get()
        if tourn.stage_compl not in valid_stages:
            abort(400, f"Invalid action '{action}' for stage '{tourn.cur_stage}'")
    elif TOURN_INIT not in valid_stages:
        abort(400, f"No active tournament for action '{action}'")
    return globals()[action](request.form)

##################
# /tourn actions #
##################

def select_tourn(form: dict) -> str:
    """Resume and render default view for existing tournament, or redirect to tournament
    creation view.  Note that this admin action is not decorated (tourn_log written
    internally)!
    """
    tourn_name = form.get('tourn')
    if tourn_name == SEL_NEW:
        if db_is_initialized():
            assert session['tourn'] == db_name()
            pause_tourn({'tourn_name': db_name()})
        flash("create_new=True")
        return redirect(url_for('admin.tourn'))

    if db_is_initialized() and db_name() != tourn_name:
        assert session['tourn'] == db_name()
        pause_tourn({'tourn_name': db_name()})
    if not db_is_initialized():
        assert not session.get('tourn')
        db_init(tourn_name, force=True)
        session['tourn'] = tourn_name
        log.info(f"setting tourn = '{tourn_name}' in session state")
        tourn = TournInfo.get()
        oper = "operation" if tourn.stage_compl in ACTIVE_STAGES else "creation"
        flash(f"info=Resuming {oper} of tournament \"{tourn_name}\"")
        # one-off log entry (parent action not decorated)
        TournLog.add(TournEvent.ADMIN_ACTION, 'select_tourn', f"Resuming {oper}")
    return redirect(url_for('index'))

def create_tourn(form: dict) -> str:
    """Create new tournament from form data (called against the `tourn_info` form).  Note
    that this admin action is not decorated (no tourn_log entry written)!
    """
    tourn       = None
    roster_path = None
    err_msg     = None
    partial     = bool(session.get('tourn'))

    tourn_name  = form.get('tourn_name')
    dates       = form.get('dates') or None
    venue       = form.get('venue') or None
    tourn_fmt   = form.get('tourn_fmt') or None
    dflt_pw     = form.get('dflt_pw') or None
    overwrite   = typecast(form.get('overwrite', ""))
    req_file    = request.files.get('roster_file')
    if req_file:
        roster_file = secure_filename(req_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_file)
        req_file.save(roster_path)
        if dflt_pw:
            dflt_pw_hash = generate_password_hash(dflt_pw)
        else:
            dflt_pw_hash = None
        try:
            db_init(tourn_name, force=True)
            attrs = {
                'dates'       : dates,
                'venue'       : venue,
                'tourn_fmt'   : tourn_fmt,
                'dflt_pw_hash': dflt_pw_hash
            }
            tourn = tourn_create(force=overwrite, **attrs)
            upload_roster(roster_path)
            db_prepare()  # archive previous checkpoint files, etc.
            tourn = TournInfo.get()
            session['tourn'] = tourn.name
            log.info(f"setting tourn = '{tourn.name}' in session state")
            return render_view(View.PLAYERS)  # TODO: let `index` do the routing for us!!!
        except OperationalError as e:
            if re.fullmatch(r'table "\w+" already exists', str(e)):
                db_reset(force=True)
                err_msg = (f'Tournament "{tourn_name}" already exists; either check the '
                           '"Overwrite Existing" box or specify a new name')
            else:
                err_msg = cap_first(str(e))
            # FALLTHROUGH
        except RuntimeError as e:
            db_reset(force=True)
            err_msg = cap_first(str(e))
            # FALLTHROUGH
        # FALLTHROUGH
    else:
        err_msg = "Roster file required (manual roster creation not yet supported)"

    tourn = TournInfo(name=tourn_name, dates=dates, venue=venue, tourn_fmt=tourn_fmt)
    context = {
        'tourn'      : tourn,
        'overwrite'  : overwrite,
        'roster_path': roster_path,
        'new_tourn'  : not partial,
        'no_roster'  : True,
        'err_msg'    : err_msg
    }
    return render_tourn(context)

def update_tourn(form: dict) -> str:
    """Update tournament information from form data (called against the `tourn_info` form,
    selected fields only).  Note that this admin action is not decorated (tourn_log
    written internally)!
    """
    tourn_name = form.get('tourn_name')
    tourn = TournInfo.get()
    assert tourn.name == tourn_name
    assert db_is_initialized()
    assert db_name() == tourn_name

    dates = form.get('dates') or None
    venue = form.get('venue') or None
    dflt_pw = form.get('dflt_pw') or None

    pw_exists = bool(tourn.dflt_pw_hash)
    if pw_exists:
        pw_upd = dflt_pw != DUMMY_PW_STR
    else:
        pw_upd = bool(dflt_pw)
    if pw_upd and dflt_pw:
        dflt_pw_hash = generate_password_hash(dflt_pw)
    else:
        dflt_pw_hash = None

    if dates != tourn.dates:
        tourn.dates = dates
    if venue != tourn.venue:
        tourn.venue = venue
    if pw_upd:
        tourn.dflt_pw_hash = dflt_pw_hash  # might be None (to clear)
    nrecs = tourn.save()
    if nrecs > 0:
        if not pw_upd:
            written = "untouched" if dflt_pw_hash else "kept empty"
        elif pw_exists:
            written = "updated" if dflt_pw_hash else "cleared"
        else:
            assert dflt_pw_hash
            written = "value set"
        log.info(f"update_tourn: dflt_pw_hash {written}")
        flash("info=Tournament information updated")
        # one-off log entry (parent action not decorated)
        upd_data = {'dates': dates, 'venue': venue, 'dflt_pw_hash': f"[{written}]"}
        TournLog.add(TournEvent.ADMIN_ACTION, 'update_tourn', ev_data=upd_data)
    else:
        flash("info=No updates specified")

    return redirect(url_for('admin.tourn'))

@admin_action
def pause_tourn(form: dict) -> str:
    """Disconnect server from current database (tourn_log written through decorator).
    """
    tourn_name = form.get('tourn_name')
    tourn = TournInfo.get()
    assert tourn.name == tourn_name
    assert db_is_initialized()
    assert db_name() == tourn_name
    db_reset(force=True)
    clear_schema_cache()
    clear_dash_storage()
    popped = session.pop('tourn', None)
    assert popped == tourn_name
    if tourn.stage_compl in ACTIVE_STAGES:
        flash(f"info=Tournament \"{tourn_name}\" has been paused")
    return redirect(url_for('index'))

####################
# /players actions #
####################

@admin_action
def gen_player_nums(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        generate_player_nums()
    return render_view(View.PLAYERS)

@admin_action
def gen_seed_bracket(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        build_seed_bracket()
    return render_view(View.SEEDING)

####################
# /seeding actions #
####################

@admin_action
def fake_seed_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        fake_seed_games()
    return render_view(View.SEEDING)

@admin_action
def tabulate_seed_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        validate_seed_round(finalize=True)
        compute_player_ranks(finalize=True)
        prepick_champ_partners()
    return render_view(View.PARTNERS)

#####################
# /partners actions #
#####################

@admin_action
def fake_partner_picks(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        fake_pick_partners()
    return render_view(View.PARTNERS)

@admin_action
def comp_team_seeds(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        build_tourn_teams()
        compute_team_seeds(finalize=True)
    return render_view(View.TEAMS)

##################
# /teams actions #
##################

@admin_action
def gen_tourn_brackets(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        build_tourn_bracket()
    return render_view(View.ROUND_ROBIN)

########################
# /round_robin actions #
########################

@admin_action
def fake_tourn_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        fake_tourn_games()
    return render_view(View.ROUND_ROBIN)

@admin_action
def tabulate_tourn_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        validate_tourn(finalize=True)
        compute_team_ranks(finalize=True)
    return render_view(View.FINAL_FOUR)

#######################
# /final_four actions #
#######################

@admin_action
def gen_semis_bracket(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        build_playoff_bracket(Bracket.SEMIS)
    return render_view(View.PLAYOFFS)

@admin_action
def gen_finals_bracket(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        build_playoff_bracket(Bracket.FINALS)
    return render_view(View.PLAYOFFS)

#####################
# /playoffs actions #
#####################

@admin_action
def fake_semis_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        fake_playoff_games(Bracket.SEMIS)
    return render_view(View.PLAYOFFS)

@admin_action
def tabulate_semis_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        validate_playoffs(Bracket.SEMIS, finalize=True)
        compute_playoff_ranks(Bracket.SEMIS, finalize=True)
    return render_view(View.FINAL_FOUR)

@admin_action
def fake_finals_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        fake_playoff_games(Bracket.FINALS)
    return render_view(View.PLAYOFFS)

@admin_action
def tabulate_finals_results(form: dict) -> str:
    """
    """
    with db_atomic() as txn:
        validate_playoffs(Bracket.FINALS, finalize=True)
        compute_playoff_ranks(Bracket.FINALS, finalize=True)
        compute_final_ranks(finalize=True)  # TODO: move this to its own action!!!
    return render_view(View.FINAL_FOUR)

#############
# renderers #
#############

SEL_SEP = "----------------"
SEL_NEW = "(create new)"

BTN_DISABLED = ' disabled'

# tuples: (url, label, link enabled starting stage)
LINK_INFO = {
    View.SEEDING: [
        ('/chart/sd_bracket',   "Seeding Round Bracket", TournStage.SEED_BRACKET),
        ('/chart/sd_scores',    "Seeding Round Scores",  TournStage.SEED_BRACKET),
        ('/dash/sd_dash',       "Live Dashboard",        TournStage.SEED_BRACKET),
        ('/chart/sd_results',   "Seeding Round Results", TournStage.SEED_RANKS)
    ],
    View.PARTNERS: [
        ('/dash/pt_dash',       "Live Dashboard",        TournStage.SEED_RANKS)
    ],
    View.TEAMS: [
        ('/chart/tm_seeds',     "Team Seed Details",     TournStage.TEAM_SEEDS),
        ('/chart/trn_results',  "Team Rank Results",     TournStage.TOURN_RANKS),
        ('/report/trn_tbreak',  "Tie-Breaker Report",    TournStage.TOURN_RANKS)
    ],
    View.ROUND_ROBIN: [
        ('/chart/rr_brackets',  "Round Robin Brackets",  TournStage.TOURN_BRACKET),
        ('/chart/rr_scores',    "Round Robin Scores",    TournStage.TOURN_BRACKET),
        ('/dash/rr_dash',       "Live Dashboard",        TournStage.TOURN_BRACKET),
        ('/chart/div_results',  "Round Robin Results",   TournStage.TOURN_RANKS),
        ('/report/rr_tbreak',   "Tie-Breaker Report",    TournStage.TOURN_RANKS)
    ],
    View.FINAL_FOUR: [
        ('/chart/fnl_results',  "Final Tournament Results", TournStage.TOURN_FINAL),
        ('/report/fnl_tbreak',  "Tie-Breaker Report",    TournStage.TOURN_FINAL)
    ],
    View.PLAYOFFS: [
        ('/dash/ff_dash',       "Live Playoff Bracket",  TournStage.SEMIS_BRACKET)
    ]
}

def render_tourn(context: dict) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    buttons = VIEW_ACTIONS[View.TOURN]
    btn_info = [ACTION_INFO[btn] for btn in buttons]

    stage_compl = TOURN_INIT
    if context.get('tourn'):
        stage_compl = context['tourn'].stage_compl or TOURN_INIT
    btn_lbl = []
    btn_attr = []
    for label, stages in btn_info:
        btn_lbl.append(label)
        btn_attr.append('' if stage_compl in stages else BTN_DISABLED)

    base_ctx = {
        'title'    : APP_NAME,
        'user'     : current_user,
        'tourn_sel': get_tourns() + [SEL_SEP, SEL_NEW],
        'sel_sep'  : SEL_SEP,
        'sel_new'  : SEL_NEW,
        'dummy_pw' : DUMMY_PW_STR,
        'tourn'    : None,   # context may contain override
        'new_tourn': False,  # ditto
        'no_roster': False,  # ditto
        'buttons'  : buttons,
        'btn_lbl'  : btn_lbl,
        'btn_attr' : btn_attr,
        'help_txt' : help_txt,
        'err_msg'  : None,   # context may contain override
        'info_msg' : None    # ditto
    }
    return render_response(TOURN_TEMPLATE, **(base_ctx | context))

def render_view(view: View) -> str:
    """Render the specified view using redirect (to be called from POST action handlers).
    Note that we are not passing any context information as query string params, so all
    information must be conveyed through the session object.
    """
    return redirect(view_path(view))

def render_admin(context: dict) -> str:
    """Common post-processing of context before rendering the main app page through Jinja
    """
    view = context.get('view')
    assert view in VIEW_DEFS
    assert view in VIEW_ACTIONS
    tourn = context.get('tourn')
    assert tourn
    exclude = POWER_ACTIONS
    if tourn.config['production_mode']:
        exclude += TEST_ACTIONS
    buttons = [btn for btn in VIEW_ACTIONS[view] if btn not in exclude]
    btn_info = [ACTION_INFO[btn] for btn in buttons]

    stage_compl = tourn.stage_compl or TOURN_INIT
    btn_lbl = []
    btn_attr = []
    for label, stages in btn_info:
        btn_lbl.append(label)
        btn_attr.append('' if stage_compl in stages else BTN_DISABLED)

    view_info = VIEW_DEFS[view]
    # TEMP: for now, do this manual hack for testing--really need to put a little
    # structure around conditional view_info (will still be hacky, though)!!!
    if view == View.PLAYERS:
        if stage_compl >= TournStage.SEED_RANKS:
            view_info = ViewInfo(
                "Players",
                pl_layout,
                "nick_name",
                [11],  # player_rank_eff
                3
            )
    elif view == View.TEAMS:
        if stage_compl >= TournStage.SEMIS_RANKS:
            view_info = ViewInfo(
                "Teams",
                tm_layout,
                "team_name",
                [14],  # final_rank_eff
                2
            )
        elif stage_compl >= TournStage.TOURN_RANKS:
            view_info = ViewInfo(
                "Teams",
                tm_layout,
                "team_name",
                [13],  # tourn_rank_eff
                2
            )
    elif view == View.FINAL_FOUR:
        if stage_compl >= TournStage.TOURN_RANKS:
            view_info = ViewInfo(
                "Final Four",
                ff_layout,
                "team_name",
                [12, 1],  # playoff_rank, tourn_rank_eff
                2
            )

    reload_int = cfg['reload_int'] if view_active(view) else -1
    base_ctx = {
        'title'     : APP_NAME,
        'user'      : current_user,
        'tourn'     : None,  # context may contain override
        'view'      : view,  # also represents relative path name
        'view_info' : view_info,
        'view_menu' : view_menu(),
        'buttons'   : buttons,
        'btn_lbl'   : btn_lbl,
        'btn_attr'  : btn_attr,
        'links'     : LINK_INFO.get(view),
        'help_txt'  : help_txt,
        'reload_int': reload_int,
        'err_msg'   : None,  # context may contain override
        'info_msg'  : None   # ditto
    }
    return render_response(ADMIN_TEMPLATE, **(base_ctx | context))

#########################
# content / metacontent #
#########################

err_txt = {
    # id: (error, description)
}

help_txt = {
    # tag: help text
}
