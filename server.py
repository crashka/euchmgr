#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Simple frontend for managing euchre tournaments Beta-style

To start the server (local usage only)::

  $ python -m server

or::

  $ flask --app server run [--debug]

To run the application, open a browser window and navigate to ``localhost:5050``.  The
usage of the application should be pretty self-explanatory.

To do list:

"""

from typing import NamedTuple
from enum import StrEnum
from glob import glob
import os.path
import re

from ckautils import typecast
from peewee import OperationalError
from flask import (Flask, request, session, render_template, Response, abort, redirect,
                   url_for, flash, get_flashed_messages)
from flask_session import Session
from cachelib.file import FileSystemCache
from werkzeug.utils import secure_filename
from flask_login import current_user, login_user, logout_user

from core import DATA_DIR, UPLOAD_DIR
from security import EuchmgrUser, ADMIN_USER, ADMIN_ID, AdminUser, EuchmgrLogin
from database import DB_FILETYPE, db_init, db_connect, db_close, db_is_closed
from schema import TournStage, TournInfo, Player
from euchmgr import (tourn_create, upload_roster, generate_player_nums, build_seed_bracket,
                     fake_seed_games, validate_seed_round, compute_player_ranks,
                     prepick_champ_partners, fake_pick_partners, build_tourn_teams,
                     compute_team_seeds, build_tourn_bracket, fake_tourn_games,
                     validate_tourn, compute_team_ranks)
from data import (data, DISABLED, CHECKED, Layout, pl_layout, sg_layout, pt_layout,
                  tm_layout, tg_layout)
from chart import chart
from dash import dash
from report import report
from mobile import mobile, is_mobile, render_error

#################
# utility stuff #
#################

# do not downcase the rest of the string like str.capitalize()
cap_first = lambda x: x[0].upper() + x[1:]

def get_logins() -> list[tuple[str, str]]:
    """Login identifiers are tuples of nick_name (index into `Player`) and familiar
    display name
    """
    if db_is_closed():
        return []
    pl_sel = Player.select().order_by(Player.last_name)
    friendly = lambda x: x.nick_name if x.nick_name != x.last_name else x.first_name
    return [(pl.nick_name, pl.display_name) for pl in pl_sel]

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

#############
# app stuff #
#############

class Config:
    """Base class for flask configuration
    """
    SESSION_TYPE = 'cachelib'
    SESSION_CACHELIB = FileSystemCache(cache_dir="sessions", default_timeout=0)

# instantiate extensions globally
sess_ext = Session()
login = EuchmgrLogin()

def create_app(config: object | Config = Config) -> Flask:
    """Application factory for the euchmgr server.  Configuration may be specified as a
    class (e.g. `Config` subclass) or `Config` instance.
    """
    app = Flask(__name__)

    app.config.from_object(config)
    app.register_blueprint(mobile, url_prefix="/mobile")
    app.register_blueprint(data, url_prefix="/data")
    app.register_blueprint(chart, url_prefix="/chart")
    app.register_blueprint(dash, url_prefix="/dash")
    app.register_blueprint(report, url_prefix="/report")
    app.jinja_env.add_extension('jinja2.ext.loopcontrols')

    global sess_ext, login
    sess_ext.init_app(app)
    login.init_app(app)

    @login.user_loader
    def load_user(user_id: str | int) -> EuchmgrUser:
        """Return "user" flask_login object, which in our case is a `Player` instance (or the
        special admin security object).
        """
        if isinstance(user_id, str):
            user_id = typecast(user_id)
        assert isinstance(user_id, int)
        if user_id == ADMIN_ID:
            return AdminUser()
        if db_is_closed():
            return None
        return Player.get(user_id)

    @app.before_request
    def _db_connect() -> None:
        """Make sure we're connected to the right database on the way in.  Mobile users have
        no explicit association with a tournament name, so they connect to whatever database
        is active.
        """
        tourn_name = session.get('tourn')
        assert not (tourn_name and is_mobile())
        if tourn_name != SEL_NEW:
            if not app.testing or db_is_closed():
                db_connect(tourn_name)

    @app.teardown_request
    def _db_close(exc) -> None:
        """Do a logical close of the database connection on the way out.  Underneath, we may
        actually choose to keep the connection open and reuse it (in which case, there may be
        no way to explicitly close it on server exit).
        """
        db_close()

    ###############
    # login stuff #
    ###############

    @app.get("/login")
    def login_page() -> str:
        """Responsive login page (entry point for players and admin).
        """
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        err_msg = "<br>".join(get_flashed_messages())
        context = {'err_msg': err_msg}
        return render_login(context)

    @app.post("/login")
    def login() -> str:
        """Log in as the specified user (player or admin)
        """
        username = request.form['username']
        if username == ADMIN_USER:
            admin = AdminUser()
            login_user(admin)
            return redirect(url_for('index'))

        player = Player.fetch_by_name(username)
        if not player:
            return render_error(400, "Bad Login", f"Invalid player name '{username}'")
        login_user(player)
        # TEMP: need to make the routing device and/or context sensitive!!!
        assert is_mobile()
        return redirect('/mobile/')

    @app.route('/logout')
    def logout():
        """Log out the current user.  Note that this call, for admins, does not reset the
        server database identification and/or connection state.
        """
        user = current_user.name
        logout_user()
        #session.clear()  # REVISIT (coupled with revamp of /tourn)!!!
        flash(f"User \\\"{user}\\\" logged out")
        return redirect(url_for('login_page'))

    #################
    # top-level nav #
    #################

    @app.get("/")
    def index() -> str:
        """Redirects to login page or appropriate app view
        """
        if not current_user.is_authenticated:
            return redirect(url_for('login_page'))

        if is_mobile():
            return redirect('/mobile/')

        assert current_user.is_admin
        context = {
            'view': View.TOURN,
        }
        return render_tourn(context)

    @app.get("/players")
    @app.get("/seeding")
    @app.get("/partners")
    @app.get("/teams")
    @app.get("/round_robin")
    def view() -> str:
        """
        """
        tourn = TournInfo.get()
        context = {
            'tourn': tourn,
            'view' : request.path
        }
        return render_app(context)

    @app.get("/tourn")
    def tourn() -> str:
        """
        """
        if is_mobile():
            return render_error(403, desc="Mobile access unauthorized")

        tourn_name = session.get('tourn')
        if tourn_name is None:
            abort(400, "Tournament not specified")

        if tourn_name != SEL_NEW:
            # resume managing previously active tournament
            tourn = TournInfo.get()
            view = dflt_view(tourn)
            return render_view(view)

        context = {
            'tourn'    : TournInfo(),
            'view'     : View.TOURN,
            'new_tourn': True
        }
        return render_tourn(context)

    ##################
    # submit actions #
    ##################

    @app.post("/")
    @app.post("/tourn")
    @app.post("/players")
    @app.post("/seeding")
    @app.post("/partners")
    @app.post("/teams")
    @app.post("/round_robin")
    def submit() -> str:
        """Process submitted form, switch on ``submit_func``, which is validated against paths
        and values in ``SUBMIT_FUNCS``
        """
        if 'submit_func' not in request.form:
            if 'tourn' not in request.form:
                abort(400, "Invalid request, tournament not specified")
            session['tourn'] = request.form['tourn']
            return redirect(url_for('tourn'))
        func = request.form['submit_func']
        view = request.path
        if view not in SUBMIT_FUNCS:
            abort(400, f"Invalid request target '{view}'")
        if func not in SUBMIT_FUNCS[view]:
            abort(400, f"Submit func '{func}' not registered for {view}")
        return globals()[func](request.form)

    return app

##############
# view stuff #
##############

# symbolic name for view path
class View(StrEnum):
    TOURN       = '/tourn'
    PLAYERS     = '/players'
    SEEDING     = '/seeding'
    PARTNERS    = '/partners'
    TEAMS       = '/teams'
    ROUND_ROBIN = '/round_robin'

class ViewInfo(NamedTuple):
    """This is not super-pretty, but we want to make this as data-driven as possible
    """
    name:       str
    layout:     Layout
    rowid_col:  str
    tbl_order:  int
    fixed_cols: int

# only include views using APP_TEMPLATE
VIEW_INFO = {
    View.PLAYERS: ViewInfo(
        "Players",
        pl_layout,
        "nick_name",
        0,
        3
    ),
    View.SEEDING: ViewInfo(
        "Seeding",
        sg_layout,
        "label",
        0,
        3
    ),
    View.PARTNERS: ViewInfo(
        "Partners",
        pt_layout,
        "nick_name",
        1,  # player_rank
        3
    ),
    View.TEAMS: ViewInfo(
        "Teams",
        tm_layout,
        "team_name",
        1,  # team_seed
        2
    ),
    View.ROUND_ROBIN: ViewInfo(
        "Round Robin",
        tg_layout,
        "label",
        0,
        2
    )
}

STAGE_MAPPING = [
    (TournStage.TEAM_RANKS,    View.TEAMS),
    (TournStage.TOURN_RESULTS, View.ROUND_ROBIN),
    (TournStage.TEAM_SEEDS,    View.TEAMS),
    (TournStage.PARTNER_PICK,  View.PARTNERS),
    (TournStage.SEED_RESULTS,  View.SEEDING),
    (TournStage.PLAYER_NUMS,   View.PLAYERS),
]

def dflt_view(tourn: TournInfo) -> View:
    """Return most relevant view for the current stage of the tournament
    """
    if tourn.stage_start is None:
        return None
    for stage, view in STAGE_MAPPING:
        if tourn.stage_start >= stage:
            return view
    return None

################
# action stuff #
################

SUBMIT_FUNCS = {
    View.TOURN: [
        'create_tourn',
        'update_tourn'
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
    ]
}

def create_tourn(form: dict) -> str:
    """Create new tournament from form data.
    """
    tourn       = None
    new_tourn   = False
    roster_file = None
    err_msg     = None

    assert session['tourn'] == SEL_NEW
    tourn_name  = form.get('tourn_name')
    timeframe   = form.get('timeframe') or None
    venue       = form.get('venue') or None
    overwrite   = form.get('overwrite')
    req_file    = request.files.get('roster_file')
    if req_file:
        roster_file = secure_filename(req_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_file)
        req_file.save(roster_path)

    try:
        db_init(tourn_name, force=True)
        tourn = tourn_create(timeframe=timeframe, venue=venue, force=bool(overwrite))
        if req_file:
            upload_roster(roster_path)
            tourn = TournInfo.get()
            session['tourn'] = tourn.name
            return render_view(View.PLAYERS)
        else:
            err_msg = "Roster file required (manual roster creation not yet supported)"
    except OperationalError as e:
        if re.fullmatch(r'table "(\w+)" already exists', str(e)):
            err_msg = f"Tournament \"{tourn_name}\" already exists; either check \"Overwrite Existing\" or specify a new name"
        else:
            err_msg = cap_first(str(e))
        tourn = TournInfo(name=tourn_name, timeframe=timeframe, venue=venue)
        new_tourn = True

    context = {
        'tourn'      : tourn,
        'view'       : View.TOURN,
        'new_tourn'  : new_tourn,
        'overwrite'  : overwrite,
        'roster_file': roster_file,
        'err_msg'    : err_msg
    }
    return render_tourn(context)

def update_tourn(form: dict) -> str:
    """Similar to `create_tourn` except that new TournInfo record has been created, so we
    only need to make sure roster file is uploaded.  We also support the updating of other
    field information.
    """
    tourn       = None
    new_tourn   = False
    roster_file = None
    err_msg     = None

    assert session['tourn'] == SEL_NEW
    tourn_name  = form.get('tourn_name')
    timeframe   = form.get('timeframe') or None
    venue       = form.get('venue') or None
    req_file    = request.files.get('roster_file')
    if req_file:
        roster_file = secure_filename(req_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_file)
        req_file.save(roster_path)

    try:
        db_init(tourn_name, force=True)
        tourn = TournInfo.get(requery=True)
        tourn.timeframe = timeframe
        tourn.venue = venue
        tourn.save()
        if req_file:
            upload_roster(roster_path)
            tourn = TournInfo.get()
            session['tourn'] = tourn.name
            return render_view(View.PLAYERS)
        else:
            err_msg = "Roster file required (manual roster creation not yet supported)"
    except OperationalError as e:
        err_msg = cap_first(str(e))
        tourn = TournInfo(name=tourn_name, timeframe=timeframe, venue=venue)
        new_tourn = True

    context = {
        'tourn'      : tourn,
        'view'       : View.TOURN,
        'new_tourn'  : new_tourn,
        'roster_file': roster_file,
        'err_msg'    : err_msg
    }
    return render_tourn(context)

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

def gen_tourn_brackets(form: dict) -> str:
    """
    """
    build_tourn_bracket()
    return render_view(View.ROUND_ROBIN)

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
    return render_view(View.TEAMS)

#############
# renderers #
#############

APP_NAME = "Euchre Manager"
APP_TEMPLATE = "app.html"
LOGIN_TEMPLATE = "login.html"
TOURN_TEMPLATE = "tourn.html"

SEL_SEP = "----------------"
SEL_NEW = "(create new)"

# keys: button name (must be kept in sync with SUBMIT_FUNCS above)
# values: tuple(button label, list of stages for which button is enabled)
BUTTON_INFO = {
    'create_tourn'          : ("Create Tournament",           None),
    'update_tourn'          : ("Create Tournament",           None),
    'gen_player_nums'       : ("Generate Player Nums",        [TournStage.PLAYER_ROSTER,
                                                               TournStage.PLAYER_NUMS]),
    'gen_seed_bracket'      : ("Create Seeding Bracket",      [TournStage.PLAYER_NUMS]),
    'fake_seed_results'     : ("Generate Fake Results",       [TournStage.SEED_BRACKET,
                                                               TournStage.SEED_RESULTS]),
    'tabulate_seed_results' : ("Tabulate Results",            [TournStage.SEED_RESULTS]),
    'fake_partner_picks'    : ("Generate Fake Picks",         [TournStage.SEED_RANKS]),
    'comp_team_seeds'       : ("Compute Team Seeds",          [TournStage.PARTNER_PICK]),
    'gen_tourn_brackets'    : ("Create Round Robin Brackets", [TournStage.TEAM_SEEDS]),
    'fake_tourn_results'    : ("Generate Fake Results",       [TournStage.TOURN_BRACKET,
                                                               TournStage.TOURN_RESULTS]),
    'tabulate_tourn_results': ("Tabulate Results",            [TournStage.TOURN_RESULTS])
}

LINK_INFO = {
    View.SEEDING    : [('/chart/sd_bracket',    "Seeding Round Bracket"),
                       ('/chart/sd_scores',     "Seeding Round Scores"),
                       ('/dash/sd_dash',        "Live Dashboard")],
    View.ROUND_ROBIN: [('/chart/rr_brackets',   "Round Robin Brackets"),
                       ('/chart/rr_scores',     "Round Robin Scores"),
                       ('/dash/rr_dash',        "Live Dashboard"),
                       ('/report/rr_tb_report', "Tie-Breaker Report")]
}

def render_view(view: View) -> str:
    """Render the specified view using redirect (to be called from POST action handlers).
    Note that we are not passing any context information as query string params, so all
    information must be conveyed through the session object.
    """
    return redirect(view)

def render_tourn(context: dict) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    view = context.get('view')
    assert view in SUBMIT_FUNCS
    buttons = SUBMIT_FUNCS[view]
    btn_info = [BUTTON_INFO[btn] for btn in buttons]
    btn_lbl = [info[0] for info in btn_info]
    btn_attr = [''] * len(btn_info)

    base_ctx = {
        'title'    : APP_NAME,
        'tourn_sel': get_tourns() + [SEL_SEP, SEL_NEW],
        'sel_sep'  : SEL_SEP,
        'sel_new'  : SEL_NEW,
        'tourn'    : None,       # context may contain override
        'new_tourn': None,       # ditto
        'err_msg'  : None,       # ditto
        'view_path': view,
        'buttons'  : buttons,
        'btn_lbl'  : btn_lbl,
        'btn_attr' : btn_attr,
        'help_txt' : help_txt
    }
    return render_template(TOURN_TEMPLATE, **(base_ctx | context))

def render_app(context: dict) -> str:
    """Common post-processing of context before rendering the main app page through Jinja
    """
    view = context.get('view')
    assert view in VIEW_INFO
    view_chk = {v: '' for v in VIEW_INFO}
    view_chk[view] = CHECKED
    assert view in SUBMIT_FUNCS
    buttons = SUBMIT_FUNCS[view]
    btn_info = [BUTTON_INFO[btn] for btn in buttons]

    stage_compl = 0
    if context.get('tourn'):
        stage_compl = context['tourn'].stage_compl or 0
    btn_lbl = []
    btn_attr = []
    for label, stages in btn_info:
        btn_lbl.append(label)
        btn_attr.append('' if stage_compl in stages else DISABLED)

    base_ctx = {
        'title'    : APP_NAME,
        'tourn'    : None,       # context may contain override
        'err_msg'  : None,       # ditto
        'view_defs': VIEW_INFO,
        'view_path': view,
        'view_chk' : view_chk,
        'view_info': VIEW_INFO[view],
        'buttons'  : buttons,
        'btn_lbl'  : btn_lbl,
        'btn_attr' : btn_attr,
        'links'    : LINK_INFO.get(view),
        'help_txt' : help_txt
    }
    return render_template(APP_TEMPLATE, **(base_ctx | context))

def render_login(context: dict) -> str:
    """Identify the user (player or admin), with relevant security applied
    """
    logins = None
    if is_mobile():
        logins = get_logins()
        if not logins:
            return render_error(503, *err_txt['not_running'])

    base_ctx = {
        'title'     : APP_NAME,
        'logins'    : logins,
        'admin_user': ADMIN_USER,
        'err_msg'   : None
    }
    return render_template(LOGIN_TEMPLATE, **(base_ctx | context))

#########################
# content / metacontent #
#########################

err_txt = {
    # id: (error, description)
    'not_running': ("Euchre Manager not running",
                    "Reload page after admin restarts the server app")
}

help_txt = {
    # tag: help text
}

############
# __main__ #
############

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5050)
