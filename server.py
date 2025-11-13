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
from flask import Flask, session, request, render_template, Response, abort

from core import DATA_DIR
from database import DB_FILETYPE
from schema import TournInfo
from euchmgr import db_init, tourn_create, generate_player_nums

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

################
# Flask Routes #
################

SUBMIT_FUNCS = [
    'create_tourn',
    'archive_tourn',
    'upload_roster',
    'gen_player_nums',
    'gen_seed_bracket',
    'fake_seed_results',
    'tabulate_seed_results',
    'fake_partner_picks',
    'gen_tourn_brackets',
    'fake_tourn_results',
    'tabulate_tourn_results'
]

@app.get("/")
def index():
    """
    """
    tourn = None
    new_tourn = None

    sel_tourn = request.args.get('sel_tourn')
    if sel_tourn:
        db_init(sel_tourn)
        if sel_tourn == SEL_NEW:
            tourn = TournInfo()
            new_tourn = True
        else:
            tourn = TournInfo.get()
            new_tourn = False

    context = {
        'tourn'    : tourn,
        'new_tourn': new_tourn
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

def create_tourn(form: dict) -> str:
    """
    """
    tourn_name = form.get('tourn_name')
    timeframe  = form.get('timeframe') or None
    venue      = form.get('venue') or None
    overwrite  = form.get('overwrite')
    db_init(tourn_name)
    tourn = tourn_create(timeframe=timeframe, venue=venue, force=bool(overwrite))

    create_msg = f"Tournament \"{tourn_name}\" created..."
    context = {
        'tourn'    : tourn,
        'info_msg' : create_msg
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
