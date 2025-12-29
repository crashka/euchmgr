# -*- coding: utf-8 -*-

"""Blueprint for the mobile device interface
"""
import re
from http import HTTPStatus

from peewee import InterfaceError
from flask import Blueprint, request, session, render_template, redirect, url_for
from flask_login import current_user

from schema import TournInfo

###################
# blueprint stuff #
###################

mobile = Blueprint('mobile', __name__)
MOBILE_TITLE = "Euchmgr"
MOBILE_TEMPLATE = "mobile.html"
ERROR_TEMPLATE = "error.html"

#################
# utility stuff #
#################

MOBILE_REGEX = r'Mobile|Android|iPhone'

def is_mobile() -> bool:
    """Determine mobile client by the user-agent string
    """
    return re.search(MOBILE_REGEX, request.user_agent.string) is not None

##############
# GET routes #
##############

@mobile.get("/")
def index() -> str:
    """Render mobile app if logged in
    """
    try:
        if not current_user.is_authenticated:
            return redirect('/login')
    except InterfaceError as e:
        if str(e).find("database must be initialized before opening a connection") > -1:
            # database not initialized, admin must be logged in--TODO: transmit error
            # condition to end-user!!!
            return redirect('/login')
        return render_error(400, "InterfaceException", str(e))

    context = {}
    return render_mobile(context)

################
# POST actions #
################

#############
# renderers #
#############

def render_mobile(context: dict) -> str:
    """Common post-processing of context before rendering the tournament selector and
    creation page through Jinja
    """
    tourn = TournInfo.get()
    
    base_ctx = {
        'title'    : MOBILE_TITLE,
        'tourn'    : tourn,
        'user'     : current_user,
        'err_msg'  : None
    }
    return render_template(MOBILE_TEMPLATE, **(base_ctx | context))

def render_error(code: int, name: str = None, desc: str = None) -> str:
    """Mobile-adjusted error page (replacement for `flask.abort`)
    """
    err = HTTPStatus(code)
    context = {
        'title'      : f"{code} {err._name_}",
        'error'      : name or err.phrase,
        'description': desc or err.description
    }
    return render_template(ERROR_TEMPLATE, **context), code
