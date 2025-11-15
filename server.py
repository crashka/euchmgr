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

from numbers import Number
from glob import glob
import os.path
import re

from ckautils import typecast
from peewee import OperationalError
from flask import Flask, session, request, render_template, Response, abort
from werkzeug.utils import secure_filename

from core import DATA_DIR, UPLOAD_DIR
from database import DB_FILETYPE
from schema import TournInfo, Player
from euchmgr import db_init, tourn_create, upload_roster

CHECKED = ' checked'

#########
# Setup #
#########

app = Flask(__name__)
#app.config.from_prefixed_env()

APP_NAME      = "Euchre Manager"
APP_TEMPLATE  = "euchmgr.html"

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
    'gen_tourn_brackets',
    'fake_tourn_results',
    'tabulate_tourn_results'
]

pl_addl_props = [
    'full_name',
    'champ'
]

pl_layout = [
    ('id',               "ID",               'hidden'),
    ('full_name',        "Name",             None),
    ('nick_name',        "Nick Name",        None),
    ('player_num',       "Player Num",       None),
    ('champ',            "Champ?",           'centered'),
    ('seed_wins',        "Seed Wins",        None),
    ('seed_losses',      "Seed Losses",      None),
    ('seed_pts_for',     "Seed Pts For",     None),
    ('seed_pts_against', "Seed Pts Against", None),
    ('player_seed',      "Seed Rank",        None)
]

@app.get("/")
def index():
    """
    """
    tourn     = None
    new_tourn = None
    view_chk  = [''] * 5

    tourn_name = request.args.get('tourn')
    if tourn_name:
        db_init(tourn_name)
        if tourn_name == SEL_NEW:
            tourn = TournInfo()
            new_tourn = True
        else:
            tourn = TournInfo.get()
            new_tourn = False

    if view := request.args.get('view'):
        view_chk[int(view)] = CHECKED

    context = {
        'tourn'    : tourn,
        'new_tourn': new_tourn,
        'view_chk' : view_chk,
        'pl_layout': pl_layout
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

@app.get("/players")
def get_players():
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    pl_list = Player.iter_players()
    pl_data = []
    for player in pl_list:
        props = {prop: getattr(player, prop) for prop in pl_addl_props}
        pl_data.append(player.__data__ | props)

    return {'data': pl_data}

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
    view_chk    = [''] * 5

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
            #view_chk[0] = CHECKED
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
        'view_chk'   : view_chk
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
    view_chk    = [''] * 5

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
            #view_chk[0] = CHECKED
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
        'view_chk'   : view_chk
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

################
# App Routines #
################

SEL_SEP = "----------------"
SEL_NEW = "(create new)"

def render_app(context: dict) -> str:
    """Common post-processing of context before rendering the main app page through Jinja
    """
    tourn_list = get_tourns() + [SEL_SEP, SEL_NEW]

    context['title']      = APP_NAME
    context['tourn_list'] = tourn_list
    context['sel_sep']    = SEL_SEP
    context['sel_new']    = SEL_NEW
    context['help_txt']   = help_txt
    context['ref_links']  = ref_links
    return render_template(APP_TEMPLATE, **context)

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
