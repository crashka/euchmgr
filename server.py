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

from ckautils import typecast
from peewee import OperationalError, IntegrityError
from flask import (Flask, Request, request, session, render_template, Response, abort,
                   redirect, url_for)
from flask_session import Session
from cachelib.file import FileSystemCache
from werkzeug.utils import secure_filename

from core import DATA_DIR, UPLOAD_DIR, ImplementationError
from database import DB_FILETYPE, now_str, db_init
from schema import GAME_PTS, TournStage, TournInfo, Player, SeedGame, Team, TournGame
from euchmgr import (get_div_teams, tourn_create, upload_roster, generate_player_nums,
                     build_seed_bracket, fake_seed_games, validate_seed_round,
                     compute_player_ranks, prepick_champ_partners, fake_pick_partners,
                     build_tourn_teams, compute_team_seeds, build_tourn_bracket,
                     fake_tourn_games, validate_tourn, compute_team_ranks)
from chart import chart
from dash import dash
from report import report

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
app.register_blueprint(chart, url_prefix="/chart")
app.register_blueprint(dash, url_prefix="/dash")
app.register_blueprint(report, url_prefix="/report")
Session(app)

# magic strings
CHECKED  = ' checked'
DISABLED = ' disabled'
HIDDEN   = 'hidden'
CENTERED = 'centered'
EDITABLE = 'editable'

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
# utility stuff #
#################

# do not downcase the rest of the string like str.capitalize()
cap_first = lambda x: x[0].upper() + x[1:]

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

############
# /players #
############

pl_addl_props = [
    'full_name',
    'champ'
]

pl_layout = [
    ('id',               "ID",           HIDDEN),
    ('full_name',        "Player",       None),
    ('player_num',       "Player Num",   EDITABLE),
    ('nick_name',        "Short Name",   None),
    ('champ',            "Champ?",       CENTERED),
    ('seed_wins',        "Seed Wins",    None),
    ('seed_losses',      "Seed Losses",  None),
    ('seed_pts_for',     "Seed Pts",     None),
    ('seed_pts_against', "Seed Opp Pts", None),
    ('player_rank',      "Seed Rank",    None)
]

@app.get("/players/data")
def get_players() -> dict:
    """
    """
    pl_iter = Player.iter_players()
    pl_data = []
    for player in pl_iter:
        pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
        pl_data.append(player.player_data | pl_props)

    return ajax_data(pl_data)

@app.post("/players/data")
def post_players() -> dict:
    """
    """
    pl_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in pl_layout if x[2] == EDITABLE}
    try:
        player = Player[data['id']]
        for col, val in upd_info.items():
            setattr(player, col, val)
        player.save()

        # NOTE: no need to update row data for now (LATER, may need this if denorm or
        # derived fields are updated when saving)
        if False:
            pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
            pl_data = player.__data__ | pl_props
    except IntegrityError as e:
        return ajax_error(str(e))

    return ajax_data(pl_data)

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

############
# /seeding #
############

sg_addl_props = [
    'player_nums'
]

sg_layout = [
    ('id',          "ID",          HIDDEN),
    ('label',       "Game",        None),
    ('round_num',   "Rnd",         None),
    ('player_nums', "Player Nums", None),
    ('team1_name',  "Team 1",      None),
    ('team2_name',  "Team 2",      None),
    ('bye_players', "Bye(s)",      None),
    ('team1_pts',   "Team 1 Pts",  EDITABLE),
    ('team2_pts',   "Team 2 Pts",  EDITABLE),
    ('winner',      "Winner",      None)
]

@app.get("/seeding/data")
def get_seeding() -> dict:
    """
    """
    sg_iter = SeedGame.iter_games(True)
    sg_data = []
    for game in sg_iter:
        sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
        sg_data.append(game.__data__ | sg_props)

    return ajax_data(sg_data)

@app.post("/seeding/data")
def post_seeding() -> dict:
    """Post scrores to seeding round game.
    """
    sg_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in sg_layout if x[2] == EDITABLE}
    team1_pts = upd_info.pop('team1_pts')
    team2_pts = upd_info.pop('team2_pts')
    assert len(upd_info) == 0
    try:
        # TODO: wrap this entire try block in a transaction!!!
        game = SeedGame[data['id']]
        game.add_scores(team1_pts, team2_pts)
        game.save()

        if game.winner:
            game.update_player_stats()
            game.insert_player_games()
            sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
            sg_data = game.__data__ | sg_props
    except RuntimeError as e:
        return ajax_error(str(e))

    return ajax_data(sg_data)

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

#############
# /partners #
#############

pt_addl_props = [
    'full_name',
    'seed_ident',
    'champ',
    'available',
    'picks_info',
    'picked_by_info'
]

pt_layout = [
    ('id',             "ID",         HIDDEN),
    ('player_rank',    "Seed Rank",  None),
    ('full_name',      "Player",     None),
    ('player_num',     "Player Num", None),
    ('seed_ident',     "Pick Order", None),
    ('champ',          "Champ?",     CENTERED),
    ('available',      "Avail?",     CENTERED),
    ('picks_info',     "Partner(s) (pick by Name or Rank)", EDITABLE),
    ('picked_by_info', "Picked By",  None)
]

@app.get("/partners/data")
def get_partners() -> dict:
    """Ajax call to load datatable for partners view.
    """
    pt_iter = Player.iter_players(by_rank=True)
    pt_data = []
    for player in pt_iter:
        pt_props = {prop: getattr(player, prop) for prop in pt_addl_props}
        pt_data.append(player.__data__ | pt_props)

    return ajax_data(pt_data)

@app.post("/partners/data")
def post_partners() -> dict:
    """Handle POST of partner pick data--the entire row is submitted, but we only look at
    the `id` and `picks_info` fields.
    """
    pt_err = None
    pt_upd = False

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in pt_layout if x[2] == EDITABLE}
    picks_info = upd_info.pop('picks_info')
    assert len(upd_info) == 0

    avail = Player.available_players(requery=True)
    if len(avail) == 0:
        return ajax_error("No available players to pick")

    player = Player[typecast(data['id'])]
    if not player.available:
        return ajax_error(f"Invalid selection; current player ({player.nick_name}) already on a team")
    if player != avail[0]:
        return ajax_error(f"Selection out of turn; active pick belongs to {avail[0].seed_ident}")

    if isinstance(picks_info, int):
        partner = Player.fetch_by_rank(picks_info)
    elif isinstance(picks_info, str):
        match = list(Player.find_by_name_pfx(picks_info))
        match_av = list(filter(lambda x: x.available, match))
        if len(match_av) > 1:
            av_by_name = sorted(match_av, key=lambda pl: pl.nick_name)
            samples = ', '.join([p.nick_name for p in av_by_name][:2]) + ", etc."
            return ajax_error(f"Multiple available matches found for name starting with \"{picks_info}\" ({samples}); please respecify pick")
        elif len(match_av) == 1:
            partner = match_av.pop()
        elif len(match) > 1:
            by_name = sorted(match, key=lambda pl: pl.nick_name)
            samples = ', '.join([p.nick_name for p in by_name][:2]) + ", etc."
            return ajax_error(f"All matches for name starting with \"{picks_info}\" ({samples}) already on a team")
        elif len(match) == 1:
            partner = match.pop()  # will get caught as unavailable, below
        else:
            partner = None
    else:
        return ajax_error(f"Cannot find player identified by \"{picks_info}\"")

    if not partner:
        return ajax_error(f"Player identified by \"{picks_info}\" does not exist")
    if not partner.available:
        return ajax_error(f"Specified pick ({partner.nick_name}) already on a team")
    if partner == player:
        return ajax_error(f"Cannot pick self ({player.nick_name}) as partner")

    # automatic final pick(s) if 2 or 3 teams remain
    assert len(avail) not in (0, 1)
    if len(avail) in (2, 3):
        partners = avail[1:]
        assert partner in partners
        player.pick_partners(*partners)
        player.save()
        avail = []
        pt_upd = True
    else:
        player.pick_partners(partner)
        player.save()
        pt_upd = True

    # REVISIT: return available players? (...and if so, by num or seed?)
    return ajax_data('all')

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

##########
# /teams #
##########

tm_addl_props = [
    'player_nums'
]

tm_layout = [
    ('id',                "ID",            HIDDEN),
    ('team_seed',         "Team Seed",     None),
    ('player_nums',       "Player Nums",   None),
    ('team_name',         "Team",          None),
    ('div_num',           "Div",           None),
    ('div_seed',          "Div Seed",      None),
    ('tourn_wins',        "Tourn Wins",    None),
    ('tourn_losses',      "Tourn Losses",  None),
    ('tourn_pts_for',     "Tourn Pts",     None),
    ('tourn_pts_against', "Tourn Opp Pts", None),
    ('tourn_rank',        "Tourn Rank",    None),
    ('div_rank',          "Div Rank",      None)
]

@app.get("/teams/data")
def get_teams() -> dict:
    """
    """
    tm_iter = Team.iter_teams()
    tm_data = []
    for team in tm_iter:
        tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
        tm_data.append(team.team_data | tm_props)

    return ajax_data(tm_data)

@app.post("/teams/data")
def post_teams() -> dict:
    """
    """
    tm_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in tm_layout if x[2] == EDITABLE}
    try:
        team = Team[data['id']]
        for col, val in upd_info.items():
            setattr(team, col, val)
        team.save()

        # NOTE: no need to update row data for now (LATER, may need this if denorm or
        # derived fields are updated when saving)
        if False:
            tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
            tm_data = team.__data__ | tm_props
    except IntegrityError as e:
        return ajax_error(str(e))

    return ajax_data(tm_data)

def gen_tourn_brackets(form: dict) -> str:
    """
    """
    build_tourn_bracket()
    return render_view(View.ROUND_ROBIN)

################
# /round_robin #
################

tg_addl_props = [
    'team_seeds'
]

tg_layout = [
    ('id',         "ID",         HIDDEN),
    ('label',      "Game",       None),
    ('div_num',    "Div",        None),
    ('round_num',  "Rnd",        None),
    ('team_seeds', "Div Seeds",  None),
    ('team1_name', "Team 1",     None),
    ('team2_name', "Team 2",     None),
    ('bye_team',   "Bye",        None),
    ('team1_pts',  "Team 1 Pts", EDITABLE),
    ('team2_pts',  "Team 2 Pts", EDITABLE),
    ('winner',     "Winner",     None)
]

@app.get("/round_robin/data")
def get_round_robin() -> dict:
    """
    """
    tg_iter = TournGame.iter_games(True)
    tg_data = []
    for game in tg_iter:
        tg_props = {prop: getattr(game, prop) for prop in tg_addl_props}
        tg_data.append(game.__data__ | tg_props)

    return ajax_data(tg_data)

@app.post("/round_robin/data")
def post_round_robin() -> dict:
    """
    """
    tg_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in tg_layout if x[2] == EDITABLE}
    team1_pts = upd_info.pop('team1_pts')
    team2_pts = upd_info.pop('team2_pts')
    assert len(upd_info) == 0
    try:
        # TODO: wrap this entire try block in a transaction!!!
        game = TournGame[data['id']]
        game.add_scores(team1_pts, team2_pts)
        game.save()

        if game.winner:
            game.update_team_stats()
            game.insert_team_games()
            tg_props = {prop: getattr(game, prop) for prop in tg_addl_props}
            tg_data = game.__data__ | tg_props
    except RuntimeError as e:
        return ajax_error(str(e))

    return ajax_data(tg_data)

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
# Renderers #
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

def ajax_data(data: dict | list | str) -> dict:
    """Wrapper for returning specified data in the structure expected by DataTables for an
    ajax data source.  `data` must be specified.
    """
    return ajax_response(True, data=data)

def ajax_succ(info_msg: str = None, data: dict | list | str = None) -> dict:
    """Convenience function (slightly shorter).  `info_msg` is optional.
    """
    return ajax_response(True, msg=info_msg, data=data)

def ajax_error(err_msg: str, data: dict | list | str = None) -> dict:
    """Convenience function (slightly shorter).  `err_msg` must be specified.
    """
    return ajax_response(False, msg=err_msg, data=data)

# type aliases
RowSelector = str

def ajax_response(succ: bool, msg: str = None, data: dict | list | str = None) -> dict:
    """Encapsulate response to an ajax request (GET or POST).  Note that clients can check
    either the `succ` or `err` field to determine the result.  The return `data` is passed
    through to the front-end, with the format being context-depedent (e.g. dict or list
    representing JSON data, or a string directive understood by the client side).

    LATER: we may want to add UI selectors as additional return elements, indicating rows
    and/or cells to highlight, set focus, etc.!!!
    """
    assert succ or msg, "`msg` arg is required for errors"
    return {
        'succ'   : succ,
        'err'    : None if succ else msg,
        'info'   : msg if succ else None,
        'data'   : data
    }

#########################
# Content / Metacontent #
#########################

help_txt = {
    # tag: help text
}

############
# __main__ #
############

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5050)
