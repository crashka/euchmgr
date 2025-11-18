#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Simple frontend for managing euchre tournaments Beta-style

To start the server (local usage only)::

  $ python -m server

or::

  $ flask --app server run [--debug]

To run the application, open a browser window and navigate to ``localhost:5000``.  The
usage of the application should be pretty self-explanatory.

To do list:

"""

from enum import IntEnum
from numbers import Number
from glob import glob
import os.path
import re

from ckautils import typecast
from peewee import OperationalError, IntegrityError
from flask import Flask, request, render_template, Response, abort, redirect, url_for
from werkzeug.utils import secure_filename

from core import DATA_DIR, UPLOAD_DIR
from database import DB_FILETYPE
from schema import TournInfo, Player, SeedGame, Team, TournGame
from euchmgr import (db_init, tourn_create, upload_roster, generate_player_nums,
                     build_seed_bracket, fake_seed_games, tabulate_seed_round,
                     compute_player_seeds, prepick_champ_partners, fake_pick_partners,
                     build_tourn_teams, compute_team_seeds, build_tourn_bracket,
                     fake_tourn_games, tabulate_tourn, compute_team_ranks)

#############
# app stuff #
#############

app = Flask(__name__)
#app.config.from_prefixed_env()

APP_NAME      = "Euchre Manager"
APP_TEMPLATE  = "euchmgr.html"

# magic strings
CHECKED  = ' checked'
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

    return tourns

#################
# utility stuff #
#################

FLOAT_PREC = 1

def round_val(val: Number) -> Number:
    """Provide the appropriate level of rounding for the leaderboard or stat value (does
    not change the number type); passthrough for non-numeric types (e.g. bool or str)
    """
    if isinstance(val, float):
        return round(val, FLOAT_PREC)
    return val

# do not downcase the rest of the string like str.capitalize()
cap_first = lambda x: x[0].upper() + x[1:]

################
# Flask Routes #
################

SUBMIT_FUNCS = [
    'create_tourn',
    'update_tourn',
    'archive_tourn',
    'create_roster',
    'gen_player_nums',
    'gen_seed_bracket',
    'fake_seed_results',
    'tabulate_seed_results',
    'fake_partner_picks',
    'comp_team_seeds',
    'gen_tourn_brackets',
    'fake_tourn_results',
    'tabulate_tourn_results'
]

@app.get("/")
def index():
    """
    """
    tourn     = None
    new_tourn = None

    tourn_name = request.args.get('tourn')
    if tourn_name:
        db_init(tourn_name)
        if tourn_name == SEL_NEW:
            tourn = TournInfo()
            new_tourn = True
        else:
            tourn = TournInfo.get()
            new_tourn = False
    view = typecast(request.args.get('view'))

    context = {
        'tourn'    : tourn,
        'new_tourn': new_tourn,
        'view'     : view
    }
    return render_app(context)

@app.post("/")
def submit():
    """Process submitted form, switch on ``submit_func``, which is validated against
    values in ``SUBMIT_FUNCS``
    """
    func = request.form['submit_func']
    if func not in SUBMIT_FUNCS:
        abort(404, f"Invalid submit func '{func}'")
    return globals()[func](request.form)

############
# /players #
############

pl_addl_props = [
    'full_name',
    'champ'
]

pl_layout = [
    ('id',               "ID",           HIDDEN),
    ('full_name',        "Name",         None),
    ('nick_name',        "Nick Name",    None),
    ('player_num',       "Player Num",   EDITABLE),
    ('champ',            "Champ?",       CENTERED),
    ('seed_wins',        "Seed Wins",    None),
    ('seed_losses',      "Seed Losses",  None),
    ('seed_pts_for',     "Seed Pts",     None),
    ('seed_pts_against', "Seed Opp Pts", None),
    ('player_seed',      "Seed Rank",    None)
]

@app.get("/players")
def get_players():
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    pl_iter = Player.iter_players()
    pl_data = []
    for player in pl_iter:
        pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
        pl_data.append(player.__data__ | pl_props)

    return {'data': pl_data}

@app.post("/players")
def post_players():
    """
    """
    pl_data = None
    pl_upd = False

    data = request.form
    upd_info = {x[0]: data.get(x[0]) for x in pl_layout if x[2] == EDITABLE}
    try:
        player = Player[data['id']]
        for col, val in upd_info.items():
            setattr(player, col, typecast(val))
        player.save()

        pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
        pl_data = player.__data__ | pl_props
        pl_upd = False
    except IntegrityError as e:
        abort(409, str(e))

    return {'data': pl_data, 'upd': pl_upd}

############
# /seeding #
############

sg_addl_props = [
    'player_nums'
]

sg_layout = [
    ('id',          "ID",          HIDDEN),
    ('label',       "Ref",         HIDDEN),
    ('round_num',   "Round",       None),
    ('table_num',   "Table",       None),
    ('player_nums', "Player Nums", None),
    ('team1_name',  "Team 1",      None),
    ('team2_name',  "Team 2",      None),
    ('bye_players', "Byes",        None),
    ('team1_pts',   "Team 1 Pts",  EDITABLE),
    ('team2_pts',   "Team 2 Pts",  EDITABLE),
    ('winner',      "Winner",      None)
]

@app.get("/seeding")
def get_seeding():
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    sg_iter = SeedGame.iter_games(True)
    sg_data = []
    for game in sg_iter:
        sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
        sg_data.append(game.__data__ | sg_props)

    return {'data': sg_data}

@app.post("/seeding")
def post_seeding():
    """
    """
    sg_data = None
    sg_upd = None

    data = request.form
    upd_info = {x[0]: data.get(x[0]) for x in sg_layout if x[2] == EDITABLE}
    try:
        game = SeedGame[data['id']]
        for col, val in upd_info.items():
            setattr(game, col, typecast(val))
        game.save()

        sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
        sg_data = game.__data__ | sg_props
        sg_upd = bool(game.winner)
    except AssertionError as e:
        abort(409, str(e))

    return {'data': sg_data, 'upd': sg_upd}

#############
# /partners #
#############

pt_addl_props = [
    'full_name',
    'champ',
    'available',
    'picks_info',
    'picked_by_info'
]

pt_layout = [
    ('id',             "ID",         HIDDEN),
    ('full_name',      "Name",       None),
    ('nick_name',      "Nick Name",  None),
    ('player_seed',    "Seed Rank",  None),
    ('champ',          "Champ?",     CENTERED),
    ('available',      "Avail?",     CENTERED),
    ('picks_info',     "Picks as Partner(s)", EDITABLE),
    ('picked_by_info', "Picked By",  None)
]

@app.get("/partners")
def get_partners():
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    pt_iter = Player.iter_players(by_seeding=True)
    pt_data = []
    for player in pt_iter:
        pt_props = {prop: getattr(player, prop) for prop in pt_addl_props}
        pt_data.append(player.__data__ | pt_props)

    return {'data': pt_data}

@app.post("/partners")
def post_partners():
    """
    """
    pt_err = None
    pt_upd = False

    data = request.form
    upd_info = {x[0]: data.get(x[0]) for x in pt_layout if x[2] == EDITABLE}
    picks_seed = typecast(upd_info.pop('picks_info', None))
    assert picks_seed
    assert len(upd_info) == 0
    partner = Player.fetch_by_seed(picks_seed)
    player_id = typecast(data['id'])
    # TODO: validate avilable and not self!!!

    # automatic final pick(s) if 2 or 3 teams remain
    avail = Player.available_players(requery=True)
    assert len(avail) not in (0, 1)
    if len(avail) in (2, 3):
        player = avail[0]
        assert player.id == player_id
        partners = avail[1:]
        assert partner in partners
        player.pick_partners(*partners)
        player.save()
        avail = []
        pt_upd = True
    else:
        player = Player[player_id]
        player.pick_partners(partner)
        player.save()
        pt_upd = True

    # REVISIT: return available players? (...and if so, by num or seed?)
    return {'err': pt_err, 'upd': pt_upd}

##########
# /teams #
##########

tm_addl_props = [
    'avg_player_seed_rnd'
]

tm_layout = [
    ('id',                "ID",            HIDDEN),
    ('team_name',         "Name",          None),
    ('team_seed',         "Team Seed",     None),
    ('avg_player_seed_rnd', "Avg Plyr Seed", None),
    ('top_player_seed',   "Top Plyr Seed", None),
    ('div_num',           "Div Num",       None),
    ('div_seed',          "Div Seed",      None),
    ('tourn_wins',        "Tourn Wins",    None),
    ('tourn_losses',      "Tourn Losses",  None),
    ('tourn_pts_for',     "Tourn Pts",     None),
    ('tourn_pts_against', "Tourn Opp Pts", None),
    ('tourn_rank',        "Tourn Rank",    None),
    ('div_rank',          "Div Rank",      None)
]

@app.get("/teams")
def get_teams():
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    tm_iter = Team.iter_teams()
    tm_data = []
    for team in tm_iter:
        tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
        tm_data.append(team.__data__ | tm_props)

    return {'data': tm_data}

@app.post("/teams")
def post_teams():
    """
    """
    tm_data = None
    tm_upd = False

    data = request.form
    upd_info = {x[0]: data.get(x[0]) for x in tm_layout if x[2] == EDITABLE}
    try:
        team = Team[data['id']]
        for col, val in upd_info.items():
            setattr(team, col, typecast(val))
        team.save()

        tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
        tm_data = team.__data__ | tm_props
        tm_upd = False
    except IntegrityError as e:
        abort(409, str(e))

    return {'data': tm_data, 'upd': tm_upd}

################
# POST actions #
################

def create_tourn(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    tourn       = None
    new_tourn   = False
    roster_fn   = None
    view        = None

    tourn_name  = form.get('tourn_name')
    timeframe   = form.get('timeframe') or None
    venue       = form.get('venue') or None
    force       = form.get('force')
    roster_file = request.files.get('roster_file')
    if roster_file:
        roster_fn = secure_filename(roster_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_fn)
        roster_file.save(roster_path)

    try:
        db_init(tourn_name)
        tourn = tourn_create(timeframe=timeframe, venue=venue, force=bool(force))
        info_msgs.append(f"Tournament \"{tourn_name}\" created")
        if roster_file:
            upload_roster(roster_path)
            info_msgs.append(f"Roster file \"{roster_fn}\" uploaded")
            view = View.PLAYERS
            tourn = TournInfo.get()
        else:
            # TEMP: prompt for uploaded in the UI!!!
            err_msgs.append("Roster file not specified")
    except OperationalError as e:
        err_msgs.append(cap_first(str(e)))
        tourn = TournInfo(name=tourn_name, timeframe=timeframe, venue=venue)
        new_tourn = True

    context = {
        'tourn'      : tourn,
        'new_tourn'  : new_tourn,
        'roster_file': roster_fn,
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def update_tourn(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    tourn       = None
    new_tourn   = False
    roster_fn   = None
    view        = None

    tourn_name  = form.get('tourn_name')
    timeframe   = form.get('timeframe') or None
    venue       = form.get('venue') or None
    roster_file = request.files.get('roster_file')
    if roster_file:
        roster_fn = secure_filename(roster_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_fn)
        roster_file.save(roster_path)

    try:
        db_init(tourn_name)
        tourn = TournInfo.get(True)
        tourn.timeframe = timeframe
        tourn.venue = venue
        tourn.save()
        info_msgs.append(f"Tournament \"{tourn_name}\" updated")
        if roster_file:
            upload_roster(roster_path)
            info_msgs.append(f"Roster file \"{roster_fn}\" uploaded")
            view = View.PLAYERS
            tourn = TournInfo.get()
        else:
            # TEMP: prompt for uploaded in the UI!!!
            err_msgs.append("Roster file not specified")
    except OperationalError as e:
        err_msgs.append(cap_first(str(e)))
        tourn = TournInfo(name=tourn_name, timeframe=timeframe, venue=venue)
        new_tourn = True

    context = {
        'tourn'      : tourn,
        'new_tourn'  : new_tourn,
        'roster_file': roster_fn,
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def create_roster(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []

    tourn_name = form.get('tourn_name')
    db_init(tourn_name)
    tourn = TournInfo.get()
    err_msgs.append("Not yet implemented!")

    context = {
        'tourn'      : tourn,
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
    }
    return render_app(context)

def gen_player_nums(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    generate_player_nums()
    view = View.PLAYERS

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def gen_seed_bracket(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    build_seed_bracket()
    view = View.SEEDING

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def fake_seed_results(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    fake_seed_games()
    view = View.SEEDING

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def tabulate_seed_results(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    tabulate_seed_round()
    compute_player_seeds()
    prepick_champ_partners()
    view = View.PARTNERS

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view_chk
    }
    return render_app(context)

def fake_partner_picks(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    fake_pick_partners()
    view = View.PARTNERS

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def comp_team_seeds(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    build_tourn_teams()
    compute_team_seeds()
    view = View.TEAMS

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def gen_tourn_brackets(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    build_tourn_bracket()
    view = View.ROUND_ROBIN

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def fake_tourn_results(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    fake_tourn_teams()
    view = View.ROUND_ROBIN

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

def tabulate_tourn_results(form: dict) -> str:
    """
    """
    info_msgs   = []
    err_msgs    = []
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    tabulate_tourn()
    compute_team_ranks()
    view = View.TEAMS

    context = {
        'tourn'      : TournInfo.get(),
        'info_msgs'  : info_msgs,
        'err_msgs'   : err_msgs,
        'view'       : view
    }
    return render_app(context)

################
# App Routines #
################

SEL_SEP = "----------------"
SEL_NEW = "(create new)"

def render_app(context: dict) -> str:
    """Common post-processing of context before rendering the main app page through Jinja
    """
    view_chk = [''] * len(View)
    view = context.get('view')
    if isinstance(view, int):
        view_chk[view] = CHECKED

    base_ctx = {
        'title'    : APP_NAME,
        'tourn_sel': get_tourns() + [SEL_SEP, SEL_NEW],
        'sel_sep'  : SEL_SEP,
        'sel_new'  : SEL_NEW,
        'view_chk' : view_chk,
        'pl_layout': pl_layout,
        'sg_layout': sg_layout,
        'pt_layout': pt_layout,
        'tm_layout': tm_layout,
        'help_txt' : help_txt,
        'ref_links': ref_links
    }
    return render_template(APP_TEMPLATE, **(base_ctx | context))

#########################
# Content / Metacontent #
#########################

help_txt = {
    # tournament select
    'tn_0': "existing database files",

    # submit buttons
    'bt_0': "Start tournament and track using the dashboard",

    # download links
    'dl_0': "directly tabulated counts (integer)",
    'dl_1': "directly tabulated counts (integer)",
    'dl_2': "format in Excel as 'Percent' (with decimal places = 1)",
    'dl_3': "format in Excel as 'Percent' (with decimal places = 1)",
    'dl_4': "stats laid out horizontally (suitable for sorting)",
    'dl_5': "stats laid out horizontally (suitable for sorting)"
}

euchplt_pfx = "https://crashka.github.io/euchre-plt/_build/html/euchplt.html#"

ref_links = {
    "Tournament": euchplt_pfx + "module-euchplt.tournament"
}

############
# __main__ #
############

if __name__ == "__main__":
    app.run(debug=True, port=5050)
