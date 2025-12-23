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

from enum import IntEnum
from glob import glob
import os.path
import re

from peewee import OperationalError
from flask import (Flask, request, session, render_template, Response, abort, redirect,
                   url_for)
from flask_session import Session
from cachelib.file import FileSystemCache
from werkzeug.utils import secure_filename

from core import DATA_DIR, UPLOAD_DIR
from database import DB_FILETYPE, db_init
from schema import TournStage, TournInfo
from euchmgr import (tourn_create, upload_roster, generate_player_nums, build_seed_bracket,
                     fake_seed_games, validate_seed_round, compute_player_ranks,
                     prepick_champ_partners, fake_pick_partners, build_tourn_teams,
                     compute_team_seeds, build_tourn_bracket, fake_tourn_games,
                     validate_tourn, compute_team_ranks)
from data import (data, DISABLED, CHECKED, pl_layout, sg_layout, pt_layout, tm_layout,
                  tg_layout)
from chart import chart
from dash import dash
from report import report

#################
# utility stuff #
#################

# do not downcase the rest of the string like str.capitalize()
cap_first = lambda x: x[0].upper() + x[1:]

#############
# app stuff #
#############

app = Flask(__name__)
APP_NAME = "Euchre Manager"
APP_TEMPLATE = "app.html"
LOGIN_TEMPLATE = "login.html"
TOURN_TEMPLATE = "tourn.html"
SESSION_TYPE = 'cachelib'
SESSION_CACHELIB = FileSystemCache(cache_dir="sessions", default_timeout=0)

app.config.from_object(__name__)
app.register_blueprint(data, url_prefix="/data")
app.register_blueprint(chart, url_prefix="/chart")
app.register_blueprint(dash, url_prefix="/dash")
app.register_blueprint(report, url_prefix="/report")
Session(app)

# app views
class View(IntEnum):
    PLAYERS     = 0
    SEEDING     = 1
    PARTNERS    = 2
    TEAMS       = 3
    ROUND_ROBIN = 4

VIEW_NAME = [
    'Players',
    'Seeding',
    'Partners',
    'Teams',
    'Round Robin'
]

VIEW_PATH = [
    '/players',
    '/seeding',
    '/partners',
    '/teams',
    '/round_robin'
]

PATH_VIEW = dict(zip(VIEW_PATH, View))

@app.before_request
def _db_init():
    """Make sure we're connected to the right database on the way in (`db_init` is smart
    about switching when the db_name changes).  Note that we optimistically do not tear
    down this connection on the way out.
    """
    tourn_name = session.get('tourn')
    if tourn_name and tourn_name != SEL_NEW:
        db_init(tourn_name)

###############
# tourn stuff #
###############

# key = input name; value = default (form input domain, i.e. string representation), if
# `form.get(param) is None`
TOURN_PARAMS = {
    'players'  : 'null',
    'teams'    : 'null',
    'thm_teams': 'null'
}

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

#################
# top-level nav #
#################

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

@app.get("/")
def index() -> str:
    """
    """
    session.clear()
    return render_tourn({})

@app.get("/players")
@app.get("/seeding")
@app.get("/partners")
@app.get("/teams")
@app.get("/round_robin")
def view() -> str:
    """
    """
    tourn = TournInfo.get()
    view = PATH_VIEW[request.path]
    context = {
        'tourn': tourn,
        'view' : view
    }
    return render_app(context)

##########
# /tourn #
##########

@app.get("/tourn")
def tourn() -> str:
    """
    """
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
        'new_tourn': True
    }
    return render_tourn(context)

##################
# submit actions #
##################

# value represents the submit target
SUBMIT_FUNCS = {
    'create_tourn'          : None,
    'update_tourn'          : None,
    'gen_player_nums'       : View.PLAYERS,
    'gen_seed_bracket'      : View.PLAYERS,
    'fake_seed_results'     : View.SEEDING,
    'tabulate_seed_results' : View.SEEDING,
    'fake_partner_picks'    : View.PARTNERS,
    'comp_team_seeds'       : View.PARTNERS,
    'gen_tourn_brackets'    : View.TEAMS,
    'fake_tourn_results'    : View.ROUND_ROBIN,
    'tabulate_tourn_results': View.ROUND_ROBIN
}

@app.post("/")
@app.post("/tourn")
@app.post("/players")
@app.post("/seeding")
@app.post("/partners")
@app.post("/teams")
@app.post("/round_robin")
def submit() -> str:
    """Process submitted form, switch on ``submit_func``, which is validated against
    values in ``SUBMIT_FUNCS``
    """
    if 'submit_func' not in request.form:
        if 'tourn' not in request.form:
            abort(400, "Invalid request, tournament not specified")
        session['tourn'] = request.form['tourn']
        return redirect(url_for('tourn'))
    func = request.form['submit_func']
    if func not in SUBMIT_FUNCS:
        abort(400, f"Invalid submit func '{func}'")
    target = SUBMIT_FUNCS[func]
    if target and request.path != VIEW_PATH[target]:
        abort(400, f"Submit func '{func}' not registered for {request.path}")
    return globals()[func](request.form)

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
        db_init(tourn_name)
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
        db_init(tourn_name)
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

SEL_SEP = "----------------"
SEL_NEW = "(create new)"
BUTTONS = list(SUBMIT_FUNCS.keys())

# button index to tuple of stages for which button is enabled
BUTTON_MAP = {
    2:  (TournStage.PLAYER_ROSTER, TournStage.PLAYER_NUMS),
    3:  (TournStage.PLAYER_NUMS,),
    4:  (TournStage.SEED_BRACKET, TournStage.SEED_RESULTS),
    5:  (TournStage.SEED_RESULTS,),
    6:  (TournStage.SEED_RANKS,),
    7:  (TournStage.PARTNER_PICK,),
    8:  (TournStage.TEAM_SEEDS,),
    9:  (TournStage.TOURN_BRACKET, TournStage.TOURN_RESULTS),
    10: (TournStage.TOURN_RESULTS,)
}

def render_view(view: View) -> str:
    """Render the specified view using redirect (to be called from POST action handlers).
    Note that we are not passing any context information as query string params, so all
    information must be conveyed through the session object.
    """
    path = VIEW_PATH[view]
    return redirect(path)

def render_tourn(context: dict) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    stage_compl = 0
    if context.get('tourn'):
        stage_compl = context['tourn'].stage_compl or 0
    btn_attr = [''] * len(BUTTONS)
    for btn_idx, btn_stages in BUTTON_MAP.items():
        if stage_compl not in btn_stages:
            btn_attr[btn_idx] += DISABLED

    base_ctx = {
        'title'    : APP_NAME,
        'tourn_sel': get_tourns() + [SEL_SEP, SEL_NEW],
        'sel_sep'  : SEL_SEP,
        'sel_new'  : SEL_NEW,
        'tourn'    : None,       # context may contain override
        'new_tourn': None,       # ditto
        'err_msg'  : None,       # ditto
        'btn_val'  : BUTTONS,
        'btn_attr' : btn_attr,
        'help_txt' : help_txt
    }
    return render_template(TOURN_TEMPLATE, **(base_ctx | context))

def render_app(context: dict) -> str:
    """Common post-processing of context before rendering the main app page through Jinja
    """
    view_chk = [''] * len(View)
    view = context.get('view')
    if isinstance(view, int):
        view_chk[view] = CHECKED

    stage_compl = 0
    if context.get('tourn'):
        stage_compl = context['tourn'].stage_compl or 0
    btn_attr = [''] * len(BUTTONS)
    for btn_idx, btn_stages in BUTTON_MAP.items():
        if stage_compl not in btn_stages:
            btn_attr[btn_idx] += DISABLED

    base_ctx = {
        'title'    : APP_NAME,
        'view_name': VIEW_NAME,
        'view_chk' : view_chk,
        'tourn'    : None,       # context may contain override
        'err_msg'  : None,       # ditto
        'pl_layout': pl_layout,
        'sg_layout': sg_layout,
        'pt_layout': pt_layout,
        'tm_layout': tm_layout,
        'tg_layout': tg_layout,
        'btn_val'  : BUTTONS,
        'btn_attr' : btn_attr,
        'help_txt' : help_txt
    }
    return render_template(APP_TEMPLATE, **(base_ctx | context))

#########################
# content / metacontent #
#########################

help_txt = {
    # tag: help text
}

############
# __main__ #
############

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5050)
