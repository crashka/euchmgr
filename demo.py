# -*- coding: utf-8 -*-

"""Blueprint for generating fake demo data
"""
import re

from ckautils import typecast
from flask import (Blueprint, request, render_template, abort, redirect, url_for, flash,
                   get_flashed_messages)

from core import ImplementationError
from euchmgr import fake_seed_games, fake_pick_partners, fake_tourn_games

###################
# blueprint stuff #
###################

demo = Blueprint('demo', __name__)
DEMO_TITLE = "Fake Demo Data"
DEMO_TEMPLATE = "demo.html"

TARGETS = {
    'seeding'     : fake_seed_games,
    'partners'    : fake_pick_partners,
    'round_robin' : fake_tourn_games
}

DFLT_TARGET = "seeding"
DFLT_NUM_RECS = 1

@demo.get("/")
def index() -> str:
    """Render demo UI popup
    """
    target   = DFLT_TARGET
    num_recs = DFLT_NUM_RECS
    err_msgs = []
    
    for msg in get_flashed_messages():
        if m := re.fullmatch(r'(\w+)=(.+)', msg):
            key, val = m.group(1, 2)
            if key == 'target':
                target = val
            elif key == 'num_recs':
                num_recs = typecast(val)
            else:
                raise ImplementationError(f"Unrecognized key '{key}' (value '{val}')")
        else:
            err_msgs.append(msg)

    context = {
        'title'   : DEMO_TITLE,
        'target'  : target,
        'num_recs': num_recs,
        'err_msg' : "<br>".join(err_msgs)
    }
    return render_template(DEMO_TEMPLATE, **context)

@demo.post("/")
def gen_data() -> str:
    """Create specified fake demo data
    """
    target = request.form.get('target')
    num_recs = typecast(request.form.get('num_recs'))

    if target not in TARGETS:
        abort(404, f"Invalid target '{target}'")

    TARGETS[target](limit=num_recs)
    flash(f"target={target}")
    flash(f"num_recs={num_recs}")
    return redirect('/demo/')
