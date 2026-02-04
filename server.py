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
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from core import DATA_DIR, UPLOAD_DIR, log, ImplementationError
from security import (current_user, DUMMY_PW_STR, EuchmgrUser, ADMIN_USER, ADMIN_ID, AdminUser,
                      EuchmgrLogin, AuthenticationError)
from database import (DB_FILETYPE, db_init, db_name, db_reset, db_is_initialized, db_connect,
                      db_close, db_is_closed)
from schema import (clear_schema_cache, TournStage, TOURN_INIT, ACTIVE_STAGES, TournInfo,
                    Player)
from euchmgr import (tourn_create, upload_roster, generate_player_nums, build_seed_bracket,
                     fake_seed_games, validate_seed_round, compute_player_ranks,
                     prepick_champ_partners, fake_pick_partners, build_tourn_teams,
                     compute_team_seeds, build_tourn_bracket, fake_tourn_games,
                     validate_tourn, compute_team_ranks)
from data import data, Layout, pl_layout, sg_layout, pt_layout, tm_layout, tg_layout
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

def create_app(config: object | Config = Config, proxied: bool = False) -> Flask:
    """Application factory for the euchmgr server.  Configuration may be specified as a
    class (e.g. `Config` subclass) or `Config` instance.
    """
    app = Flask(__name__)
    if proxied:
        print("Using ProxyFix")
        app.wsgi_app = ProxyFix(app.wsgi_app)

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

    ignore_pfx = {
        "static",
        ".well-known"
    }

    def ignore_path(path: str) -> bool:
        """Whether to ignore this path in relation to database connectivity.
        """
        pfx = path[1:].split('/', 1)[0]
        return pfx in ignore_pfx

    @app.before_request
    def _db_connect() -> None:
        """Make sure we're connected to the right database on the way in.  Mobile users have
        no explicit association with a tournament name, so they connect to whatever database
        is active.
        """
        if ignore_path(request.path):
            return
        log.debug(f"@app.before_request: {request.method} {request.path}")
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
        if ignore_path(request.path):
            return
        log.debug(f"@app.teardown_request: {request.method} {request.path}")
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

        username = None
        err_msgs = []
        # see if any secret parameters have been transmitted to us (see NOTE for `view` in
        # mobile.py--we might want to encapsulate this into a shared mechanism!)
        for msg in get_flashed_messages():
            if m := re.fullmatch(r'(\w+)=(.+)', msg):
                key, val = m.group(1, 2)
                if key == 'username':
                    username = val
                else:
                    raise ImplementationError(f"unexpected secret key '{key}' (value '{val}')")
            else:
                err_msgs.append(msg)
        err_msg = "<br>".join(err_msgs)

        context = {
            'username': username,
            'err_msg' : err_msg
        }
        return render_login(context)

    @app.post("/login")
    def login() -> str:
        """Log in as the specified user (player or admin).
        """
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USER:
            admin = AdminUser()
            try:
                admin.login(password)
            except AuthenticationError as e:
                flash(str(e))
                return redirect(url_for('login_page'))
            return redirect(url_for('index'))

        player = Player.fetch_by_name(username)
        if not player:
            return render_error(400, "Bad Login", f"Invalid player name '{username}'")
        try:
            player.login(password)
        except AuthenticationError as e:
            flash(str(e))
            flash(f"username={username}")
            return redirect(url_for('login_page'))
        # TEMP: need to make the routing device and/or context sensitive!!!
        assert is_mobile()
        return redirect('/mobile/')

    @app.route('/logout')
    def logout():
        """Log out the current user.  Note that this call, for admins, does not reset the
        server database identification and/or connection state.
        """
        if current_user.is_authenticated:
            user = current_user.name
            current_user.logout()
            flash(f"User \\\"{user}\\\" logged out")
        return redirect(url_for('login_page'))

    #################
    # top-level nav #
    #################

    @app.get("/")
    def index() -> str:
        """Redirect to login page or appropriate app view (based on current stage).
        """
        if not current_user.is_authenticated:
            return redirect(url_for('login_page'))

        if is_mobile():
            return redirect('/mobile/')

        assert current_user.is_admin
        if not db_is_initialized():
            return redirect(url_for('tourn'))

        tourn = TournInfo.get()
        tourn_name = session.get('tourn')
        if not tourn_name:
            # our session information has been cleared out somehow (should only happen in
            # testing)--let's just re-set it and log this as an event of interest
            session['tourn'] = tourn.name
            log.info(f"re-setting tourn = '{tourn.name}' in session state")

        view = dflt_view(tourn)
        return render_view(view)

    @app.get("/players")
    @app.get("/seeding")
    @app.get("/partners")
    @app.get("/teams")
    @app.get("/round_robin")
    def view() -> str:
        """Render the requested view directly.
        """
        if not current_user.is_authenticated:
            return redirect(url_for('login_page'))

        if is_mobile():
            return render_error(403, desc="Mobile access unauthorized")

        tourn = TournInfo.get()
        err_msg = "<br>".join(get_flashed_messages())

        context = {
            'tourn'  : tourn,
            'view'   : request.path,
            'err_msg': err_msg
        }
        return render_app(context)

    @app.get("/tourn")
    def tourn() -> str:
        """View used to manage tournament information, as well as create new tournaments.
        """
        if not current_user.is_authenticated:
            return redirect(url_for('login_page'))

        if is_mobile():
            return render_error(403, desc="Mobile access unauthorized")

        create_new = False
        err_msgs = []
        # see comment for same code in `login_page` (above)
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
            view = dflt_view(tourn)
            return render_view(view)
            """
            tourn = TournInfo.get()
            assert tourn.name == tourn_name
            # render admin view for existing tournament
            context = {
                'tourn'    : tourn,
                'view'     : View.TOURN,
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
            'view'     : View.TOURN,
            'new_tourn': create_new,
            'err_msg'  : err_msg
        }
        return render_tourn(context)

    ##################
    # submit actions #
    ##################

    @app.post("/tourn")
    @app.post("/players")
    @app.post("/seeding")
    @app.post("/partners")
    @app.post("/teams")
    @app.post("/round_robin")
    def submit() -> str:
        """Process submitted form, switch on ``submit_func``, which is validated against
        paths and values in ``SUBMIT_FUNCS``
        """
        if not current_user.is_authenticated:
            abort(401, f"Not authenticated")
        func = request.form['submit_func']
        view = request.path
        if view not in SUBMIT_FUNCS:
            abort(400, f"Invalid request target '{view}'")
        if func not in SUBMIT_FUNCS[view]:
            abort(400, f"Submit func '{func}' not registered for {view}")
        return globals()[func](request.form)

    # end of `def login_page()`
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
    (TournStage.TEAM_RANKS,    View.ROUND_ROBIN),
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
    ]
}

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
        return redirect(url_for('tourn'))

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
        'view'       : View.TOURN,
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

    return redirect(url_for('tourn'))

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
    return render_view(View.ROUND_ROBIN)

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
    'select_tourn'          : ("[Ceci n'existe pas]",         [None]),
    'create_tourn'          : ("Create Tournament",           [TOURN_INIT]),
    'update_tourn'          : ("Update Tournament",           list(ACTIVE_STAGES)),
    'pause_tourn'           : ("Pause Tournament",            list(ACTIVE_STAGES)),
    'gen_player_nums'       : ("Generate Player Nums",        [TournStage.PLAYER_ROSTER]),
    'gen_seed_bracket'      : ("Create Seeding Bracket",      [TournStage.PLAYER_NUMS]),
    'fake_seed_results'     : ("Generate Fake Results",       [TournStage.SEED_BRACKET]),
    'tabulate_seed_results' : ("Tabulate Results",            [TournStage.SEED_RESULTS]),
    'fake_partner_picks'    : ("Generate Fake Picks",         [TournStage.SEED_RANKS]),
    'comp_team_seeds'       : ("Compute Team Seeds",          [TournStage.PARTNER_PICK]),
    'gen_tourn_brackets'    : ("Create Round Robin Brackets", [TournStage.TEAM_SEEDS]),
    'fake_tourn_results'    : ("Generate Fake Results",       [TournStage.TOURN_BRACKET]),
    'tabulate_tourn_results': ("Tabulate Results",            [TournStage.TOURN_RESULTS])
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
        ('/report/tie_breaker', "Tie-Breaker Report",    TournStage.TEAM_RANKS)
    ]
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
    assert view in SUBMIT_FUNCS
    buttons = SUBMIT_FUNCS[view]
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
        'tourn'    : None,       # context may contain override
        'err_msg'  : None,       # ditto
        'view_defs': VIEW_INFO,
        'view_path': view,
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
    tourn = None
    logins = None
    if is_mobile():
        logins = get_logins()
        if not logins:
            return render_error(503, *err_txt['not_running'])
        tourn = TournInfo.get()

    base_ctx = {
        'title'     : APP_NAME,
        'tourn'     : tourn,  # if db connected (not needed for admin login)
        'logins'    : logins,
        'username'  : None,   # context may contain override
        'admin_user': ADMIN_USER,
        'err_msg'   : None
    }
    return render_template(LOGIN_TEMPLATE, **(base_ctx | context))

#########################
# content / metacontent #
#########################

err_txt = {
    # id: (error, description)
    'not_running': ("Euchre Manager paused",
                    "Refresh the app page after admin resumes the tournament operation")
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
