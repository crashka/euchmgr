# -*- coding: utf-8 -*-

"""Blueprint for the admin interface
"""

from typing import NamedTuple
from enum import StrEnum
from glob import glob
import os.path
import re

from ckautils import typecast
from peewee import OperationalError
from flask import Blueprint, g, request, session, abort, url_for, flash, get_flashed_messages
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from core import DATA_DIR, UPLOAD_DIR, log, ImplementationError
from security import current_user, DUMMY_PW_STR
from database import DB_FILETYPE, db_init, db_name, db_reset, db_is_initialized
from schema import (clear_schema_cache, Bracket, TournStage, TOURN_INIT, ACTIVE_STAGES,
                    TournInfo)
from euchmgr import (tourn_create, upload_roster, generate_player_nums, build_seed_bracket,
                     fake_seed_games, validate_seed_round, compute_player_ranks,
                     prepick_champ_partners, fake_pick_partners, build_tourn_teams,
                     compute_team_seeds, build_tourn_bracket, fake_tourn_games,
                     validate_tourn, compute_team_ranks, build_playoff_bracket,
                     validate_playoffs, compute_playoff_ranks)
from ui_common import is_mobile, render_response, redirect, render_error
from data import (Layout, pl_layout, sg_layout, pt_layout, tm_layout, tg_layout, ff_layout,
                  pg_layout)

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
    glob_str  = os.path.join(DATA_DIR, r'*' + DB_FILETYPE)
    match_str = os.path.join(DATA_DIR, r'(.+)' + DB_FILETYPE)

    tourns = []
    for file in glob(glob_str):
        m = re.fullmatch(match_str, file)
        assert m and len(m.groups()) == 1
        tourns.append(m.groups()[0])

    return sorted(tourns)

##############
# view stuff #
##############

class View(StrEnum):
    """Note that view names are now different than their paths (though they just happen
    to resemble relative path names)--the actual paths are now defined in VIEW_DEFS
    """
    TOURN       = 'tourn'
    PLAYERS     = 'players'
    SEEDING     = 'seeding'
    PARTNERS    = 'partners'
    TEAMS       = 'teams'
    ROUND_ROBIN = 'round_robin'
    FINAL_FOUR  = 'final_four'
    PLAYOFFS    = 'playoffs'

class ViewInfo(NamedTuple):
    """This is not super-pretty, but we want to make this as data-driven as possible
    """
    name:       str  # display name
    path:       str
    layout:     Layout
    rowid_col:  str  # column name
    tbl_order:  int  # default sort column(s) (column index)
    fixed_cols: int  # for horizontal scrolling (currently disabled)

# only include views using ADMIN_TEMPLATE
VIEW_DEFS = {
    View.PLAYERS: ViewInfo(
        "Players",
        "/players",
        pl_layout,
        "nick_name",
        [0],  # id
        3
    ),
    View.SEEDING: ViewInfo(
        "Seeding",
        "/seeding",
        sg_layout,
        "label",
        [0],  # id
        3
    ),
    View.PARTNERS: ViewInfo(
        "Partners",
        "/partners",
        pt_layout,
        "nick_name",
        [1],  # player_rank
        3
    ),
    View.TEAMS: ViewInfo(
        "Teams",
        "/teams",
        tm_layout,
        "team_name",
        [1],  # team_seed
        2
    ),
    View.ROUND_ROBIN: ViewInfo(
        "Round Robin",
        "/round_robin",
        tg_layout,
        "label",
        [0],  # id
        2
    ),
    View.FINAL_FOUR: ViewInfo(
        "Final Four",
        "/final_four",
        ff_layout,
        "team_name",
        [1],  # tourn_rank
        2
    ),
    View.PLAYOFFS: ViewInfo(
        "Playoffs",
        "/playoffs",
        pg_layout,
        "label",
        [0],  # id
        2
    )
}

def view_menu() -> list[tuple[str, str, str]]:
    """Return list of tuples representing navigation menu items of the following form:
    (view_name, view_label, view_path).
    """
    return [(str(view), info.name, info.path) for view, info in VIEW_DEFS.items()]

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
]

def active_view(tourn: TournInfo) -> View:
    """Return active view for the current stage of the tournament
    """
    if tourn.stage_start is None:
        return None
    for stage, view in STAGE_MAPPING:
        if tourn.stage_start >= stage:
            return view
    return None

##############
# GET routes #
##############

@admin.get("/tourn")
def tourn() -> str:
    """View used to manage tournament information, as well as create new tournaments.
    """
    if not current_user.is_authenticated:
        return redirect(url_for('login_page'))

    if is_mobile():
        return render_error(403, desc="Mobile access unauthorized")

    create_new = False
    err_msgs = []
    # see comment for same code in `login_page` (server.py)
    for msg in get_flashed_messages():
        if m := re.fullmatch(r'(\w+)=(.+)', msg):
            key, val = m.group(1, 2)
            if key == 'create_new':
                create_new = typecast(val)
            else:
                raise ImplementationError(f"unexpected secret key '{key}' (value '{val}')")
        else:
            err_msgs.append(msg)
    err_msg = "<br>".join(err_msgs)

    tourn_name = session.get('tourn')
    if tourn_name:
        assert not create_new
        assert db_is_initialized()
        """
        # resume managing previously active tournament
        tourn = TournInfo.get()
        assert tourn.name == tourn_name
        view = active_view(tourn)
        return redirect(view)
        """
        tourn = TournInfo.get()
        assert tourn.name == tourn_name
        # render admin view for existing tournament
        context = {
            'tourn'    : tourn,
            'err_msg'  : err_msg
        }
        return render_tourn(context)

    tourn = TournInfo() if create_new else None
    if db_is_initialized():
        # our session information has been cleared out somehow (should only happen in
        # testing)--let's just re-set it and log this as an event of interest (same as
        # for `index` above)
        tourn = TournInfo.get()
        session['tourn'] = tourn.name
        log.info(f"re-setting tourn = '{tourn.name}' in session state")

    context = {
        'tourn'    : tourn,
        'new_tourn': create_new,
        'err_msg'  : err_msg
    }
    return render_tourn(context)

@admin.get("/players")
@admin.get("/seeding")
@admin.get("/partners")
@admin.get("/teams")
@admin.get("/round_robin")
@admin.get("/final_four")
@admin.get("/playoffs")
def view() -> str:
    """Render the requested view directly.
    """
    if not current_user.is_authenticated:
        return redirect(url_for('login_page'))

    if is_mobile():
        return render_error(403, desc="Mobile access unauthorized")

    view = request.path.split('/')[-1]
    tourn = TournInfo.get()
    err_msg = "<br>".join(get_flashed_messages())

    context = {
        'tourn'  : tourn,
        'view'   : view,
        'err_msg': err_msg
    }
    return render_admin(context)

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
        'gen_seed_bracket'
    ],
    View.SEEDING: [
        'fake_seed_results',
        'tabulate_seed_results'
    ],
    View.PARTNERS: [
        'fake_partner_picks',
        'comp_team_seeds'
    ],
    View.TEAMS: [
        'gen_tourn_brackets'
    ],
    View.ROUND_ROBIN: [
        'fake_tourn_results',
        'tabulate_tourn_results'
    ],
    View.FINAL_FOUR: [
        'gen_semis_bracket',
        'gen_finals_bracket'
    ],
    View.PLAYOFFS: [
        'tabulate_semis_results',
        'tabulate_finals_results'
    ]
}

@admin.post("/tourn")
@admin.post("/players")
@admin.post("/seeding")
@admin.post("/partners")
@admin.post("/teams")
@admin.post("/round_robin")
@admin.post("/final_four")
@admin.post("/playoffs")
def view_actions() -> str:
    """Process submitted form, switch on ``action``, which is validated against
    paths and values in ``ACTIONS``
    """
    if not current_user.is_authenticated:
        abort(401, f"Not authenticated")
    action = request.form['action']
    view = request.path.split('/')[-1]
    if view not in VIEW_ACTIONS:
        abort(400, f"Invalid action target '{view}'")
    if action not in VIEW_ACTIONS[view]:
        abort(400, f"Action '{action}' not registered for {view}")
    return globals()[action](request.form)

##################
# /tourn actions #
##################

def select_tourn(form: dict) -> str:
    """Render default view for existing tournament, or new tournament creation view.  Note
    that this is called against the `select_tourn` form.
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
        flash(f"Resuming operation of tournament \"{tourn_name}\"")
    return redirect(url_for('index'))

def create_tourn(form: dict) -> str:
    """Create new tournament from form data.  Note that this is called against the
    `tourn_info` form.
    """
    tourn       = None
    roster_path = None
    err_msg     = None

    tourn_name  = form.get('tourn_name')
    dates       = form.get('dates') or None
    venue       = form.get('venue') or None
    dflt_pw     = form.get('dflt_pw') or None
    overwrite   = typecast(form.get('overwrite', ""))
    req_file    = request.files.get('roster_file')
    if not req_file:
        err_msg = "Roster file required (manual roster creation not yet supported)"
    else:
        roster_file = secure_filename(req_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_file)
        req_file.save(roster_path)
        if dflt_pw:
            dflt_pw_hash = generate_password_hash(dflt_pw)
        else:
            dflt_pw_hash = None
        try:
            assert not session.get('tourn')
            db_init(tourn_name, force=True)
            attrs = {
                'dates'       : dates,
                'venue'       : venue,
                'dflt_pw_hash': dflt_pw_hash
            }
            tourn = tourn_create(force=overwrite, **attrs)
            upload_roster(roster_path)
            tourn = TournInfo.get()
            session['tourn'] = tourn.name
            log.info(f"setting tourn = '{tourn.name}' in session state")
            return render_view(View.PLAYERS)  # TODO: let `index` do the routing for us!!!
        except OperationalError as e:
            if re.fullmatch(r'table "\w+" already exists', str(e)):
                err_msg = (f'Tournament "{tourn_name}" already exists; either check the '
                           '"Overwrite Existing" box or specify a new name')
            else:
                err_msg = cap_first(str(e))

    tourn = TournInfo(name=tourn_name, dates=dates, venue=venue)
    context = {
        'tourn'      : tourn,
        'overwrite'  : overwrite,
        'roster_path': roster_path,
        'new_tourn'  : True,
        'err_msg'    : err_msg
    }
    return render_tourn(context)

def update_tourn(form: dict) -> str:
    """Update tournament information (selected fields only) from form data.  Note that
    this is called against the `tourn_info` form.
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
        flash("Tournament information updated")
    else:
        flash("No updates specified")

    return redirect(url_for('admin.tourn'))

def pause_tourn(form: dict) -> str:
    """Disconnect server from database for current tournament.  Note that this is called
    against the `tourn_info` form.
    """
    tourn_name = form.get('tourn_name')
    tourn = TournInfo.get()
    assert tourn.name == tourn_name
    assert db_is_initialized()
    assert db_name() == tourn_name
    db_reset(force=True)
    clear_schema_cache()
    popped = session.pop('tourn', None)
    assert popped == tourn_name
    flash(f"Tournament \"{tourn_name}\" has been paused")
    return redirect(url_for('index'))

####################
# /players actions #
####################

def gen_player_nums(form: dict) -> str:
    """
    """
    generate_player_nums()
    return render_view(View.PLAYERS)

def gen_seed_bracket(form: dict) -> str:
    """
    """
    build_seed_bracket()
    return render_view(View.SEEDING)

####################
# /seeding actions #
####################

def fake_seed_results(form: dict) -> str:
    """
    """
    fake_seed_games()
    return render_view(View.SEEDING)

def tabulate_seed_results(form: dict) -> str:
    """
    """
    validate_seed_round(finalize=True)
    compute_player_ranks(finalize=True)
    prepick_champ_partners()
    return render_view(View.PARTNERS)

#####################
# /partners actions #
#####################

def fake_partner_picks(form: dict) -> str:
    """
    """
    fake_pick_partners()
    return render_view(View.PARTNERS)

def comp_team_seeds(form: dict) -> str:
    """
    """
    build_tourn_teams()
    compute_team_seeds()
    return render_view(View.TEAMS)

##################
# /teams actions #
##################

def gen_tourn_brackets(form: dict) -> str:
    """
    """
    build_tourn_bracket()
    return render_view(View.ROUND_ROBIN)

########################
# /round_robin actions #
########################

def fake_tourn_results(form: dict) -> str:
    """
    """
    fake_tourn_games()
    return render_view(View.ROUND_ROBIN)

def tabulate_tourn_results(form: dict) -> str:
    """
    """
    validate_tourn(finalize=True)
    compute_team_ranks(finalize=True)
    return render_view(View.FINAL_FOUR)

#######################
# /final_four actions #
#######################

def gen_semis_bracket(form: dict) -> str:
    """
    """
    build_playoff_bracket(Bracket.SEMIS)
    return render_view(View.PLAYOFFS)

def tabulate_semis_results(form: dict) -> str:
    """
    """
    validate_playoffs(Bracket.SEMIS, finalize=True)
    compute_playoff_ranks(Bracket.SEMIS, finalize=True)
    return render_view(View.FINAL_FOUR)

#####################
# /playoffs actions #
#####################

def gen_finals_bracket(form: dict) -> str:
    """
    """
    build_playoff_bracket(Bracket.FINALS)
    return render_view(View.PLAYOFFS)

def tabulate_finals_results(form: dict) -> str:
    """
    """
    validate_playoffs(Bracket.FINALS, finalize=True)
    compute_playoff_ranks(Bracket.FINALS, finalize=True)
    return render_view(View.FINAL_FOUR)

#############
# renderers #
#############

SEL_SEP = "----------------"
SEL_NEW = "(create new)"

# keys: button name (must be kept in sync with VIEW_ACTIONS above)
# values: tuple(button label, list of stages for which button is enabled)
BUTTON_INFO = {
    'select_tourn'           : ("[Ceci n'existe pas]",         [None]),
    'create_tourn'           : ("Create Tournament",           [TOURN_INIT]),
    'update_tourn'           : ("Update Tournament",           list(ACTIVE_STAGES)),
    'pause_tourn'            : ("Pause Tournament",            list(ACTIVE_STAGES)),
    'gen_player_nums'        : ("Generate Player Nums",        [TournStage.PLAYER_ROSTER]),
    'gen_seed_bracket'       : ("Create Seeding Bracket",      [TournStage.PLAYER_NUMS]),
    'fake_seed_results'      : ("Generate Fake Results",       [TournStage.SEED_BRACKET]),
    'tabulate_seed_results'  : ("Tabulate Results",            [TournStage.SEED_RESULTS]),
    'fake_partner_picks'     : ("Generate Fake Picks",         [TournStage.SEED_RANKS]),
    'comp_team_seeds'        : ("Compute Team Seeds",          [TournStage.PARTNER_PICK]),
    'gen_tourn_brackets'     : ("Create Round Robin Brackets", [TournStage.TEAM_SEEDS]),
    'fake_tourn_results'     : ("Generate Fake Results",       [TournStage.TOURN_BRACKET]),
    'tabulate_tourn_results' : ("Tabulate Results",            [TournStage.TOURN_RESULTS]),
    'gen_semis_bracket'      : ("Create Semifinals Bracket",   [TournStage.TOURN_RANKS]),
    'tabulate_semis_results' : ("Tabulate Semifinals Results", [TournStage.SEMIS_RESULTS]),
    'gen_finals_bracket'     : ("Create Finals Bracket",       [TournStage.SEMIS_RANKS]),
    'tabulate_finals_results': ("Tabulate Finals Results",     [TournStage.FINALS_RESULTS])
}

BTN_DISABLED = ' disabled'

# tuples: (url, label, link enabled starting stage)
LINK_INFO = {
    View.SEEDING: [
        ('/chart/sd_bracket',   "Seeding Round Bracket", TournStage.SEED_BRACKET),
        ('/chart/sd_scores',    "Seeding Round Scores",  TournStage.SEED_BRACKET),
        ('/dash/sd_dash',       "Live Dashboard",        TournStage.SEED_BRACKET)
    ],
    View.PARTNERS: [
        ('/dash/pt_dash',       "Live Dashboard",        TournStage.SEED_RANKS)
    ],
    View.ROUND_ROBIN: [
        ('/chart/rr_brackets',  "Round Robin Brackets",  TournStage.TOURN_BRACKET),
        ('/chart/rr_scores',    "Round Robin Scores",    TournStage.TOURN_BRACKET),
        ('/dash/rr_dash',       "Live Dashboard",        TournStage.TOURN_BRACKET),
        ('/report/tie_breaker', "Tie-Breaker Report",    TournStage.TOURN_RANKS)
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
    btn_info = [BUTTON_INFO[btn] for btn in buttons]

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
        'err_msg'  : None,   # ditto
        'buttons'  : buttons,
        'btn_lbl'  : btn_lbl,
        'btn_attr' : btn_attr,
        'help_txt' : help_txt
    }
    return render_response(TOURN_TEMPLATE, **(base_ctx | context))

def render_view(view: View) -> str:
    """Render the specified view using redirect (to be called from POST action handlers).
    Note that we are not passing any context information as query string params, so all
    information must be conveyed through the session object.
    """
    assert view in VIEW_DEFS
    view_path = VIEW_DEFS[view].path
    return redirect(view_path)

def render_admin(context: dict) -> str:
    """Common post-processing of context before rendering the main app page through Jinja
    """
    view = context.get('view')
    assert view in VIEW_DEFS
    assert view in VIEW_ACTIONS
    buttons = VIEW_ACTIONS[view]
    btn_info = [BUTTON_INFO[btn] for btn in buttons]

    stage_compl = TOURN_INIT
    if context.get('tourn'):
        stage_compl = context['tourn'].stage_compl or TOURN_INIT
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
                "/players",
                pl_layout,
                "nick_name",
                [11],  # player_rank
                3
            )
    elif view == View.TEAMS:
        if stage_compl >= TournStage.SEMIS_RANKS:
            view_info = ViewInfo(
                "Teams",
                "/teams",
                tm_layout,
                "team_name",
                [14],  # final_rank
                2
            )
        elif stage_compl >= TournStage.TOURN_RANKS:
            view_info = ViewInfo(
                "Teams",
                "/teams",
                tm_layout,
                "team_name",
                [13, 12],  # div_rank, tourn_rank
                2
            )
    elif view == View.FINAL_FOUR:
        if stage_compl >= TournStage.TOURN_RANKS:
            view_info = ViewInfo(
                "Final Four",
                "/final_four",
                ff_layout,
                "team_name",
                [12, 1],  # playoff_rank, tourn_rank
                2
            )

    base_ctx = {
        'title'    : APP_NAME,
        'user'     : current_user,
        'tourn'    : None,       # context may contain override
        'err_msg'  : None,       # ditto
        'view_menu': view_menu(),
        'cur_view' : view,
        'view_info': view_info,
        'buttons'  : buttons,
        'btn_lbl'  : btn_lbl,
        'btn_attr' : btn_attr,
        'links'    : LINK_INFO.get(view),
        'help_txt' : help_txt
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
