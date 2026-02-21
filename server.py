#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Simple frontend for managing euchre tournaments Beta Upsilon-style.  This module
implements the Flask "application factory" pattern through the ``create_app()`` call.
"""

import re
import traceback

from ckautils import typecast
from flask import Flask, current_app, g, request, session, url_for, flash, get_flashed_messages
from flask.globals import request_ctx
from flask_session import Session
from cachelib.file import FileSystemCache
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException

from core import log, ImplementationError
from security import (current_user, EuchmgrUser, ADMIN_USER, ADMIN_ID, AdminUser, EuchmgrLogin,
                      AuthenticationError)
from database import db_is_initialized, db_connect, db_close, db_is_closed
from schema import TournInfo
from ui import Player
from ui_common import is_mobile, render_response, redirect, render_error
from data import data
from chart import chart
from dash import dash
from report import report
from mobile import mobile, MOBILE_URL_PFX
from admin import admin, active_view, render_view, SEL_NEW

#################
# utility stuff #
#################

# do not downcase the rest of the string like str.capitalize()
cap_first = lambda x: x[0].upper() + x[1:]

def get_logins() -> list[tuple[str, str]]:
    """Login identifiers are tuples of nick_name (referenced in `Player.fetch_by_name`)
    and familiar display name
    """
    if db_is_closed():
        return []
    pl_sel = Player.select().order_by(Player.last_name)
    return [(pl.nick_name, pl.display_name) for pl in pl_sel]

#############
# app stuff #
#############

APP_NAME = "Euchre Manager"
LOGIN_TEMPLATE = "login.html"

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
        log.info("creating app using ProxyFix (default args)")
        app.wsgi_app = ProxyFix(app.wsgi_app)

    app.config.from_object(config)
    app.register_blueprint(admin)
    app.register_blueprint(data)
    app.register_blueprint(mobile, url_prefix=MOBILE_URL_PFX)
    app.register_blueprint(chart, url_prefix='/chart')
    app.register_blueprint(dash, url_prefix='/dash')
    app.register_blueprint(report, url_prefix='/report')
    app.jinja_env.add_extension('jinja2.ext.loopcontrols')

    global sess_ext, login
    sess_ext.init_app(app)
    login.init_app(app)

    @app.before_request
    def _api_handler() -> None:
        """Tag API calls on the way in (used to affect the rendering course).
        """
        g.api_call = request.path.startswith('/api/')  # bool

    ##################
    # db connections #
    ##################

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

    @app.errorhandler(HTTPException)
    def handle_http_exception(e) -> tuple[dict, int] | HTTPException:
        """Return appropropiate exception format based on `g.api_call`.
        """
        if g.api_call:
            return {
                "code": e.code,
                "name": e.name,
                "description": e.description
            }, e.code
        return e

    @app.errorhandler(Exception)
    def handle_exception(e) -> tuple[dict, int] | Exception:
        """Return appropropiate exception format based on `g.api_call`.
        """
        if g.api_call:
            tb = traceback.format_exception(e)
            return {
                "error": str(e),
                "traceback": tb if app.debug else None
            }, 500
        return e

    ###############
    # login stuff #
    ###############

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
        return redirect(url_for('mobile.index'))

    @app.route("/logout", methods=['GET', 'POST'])
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
            return redirect(url_for('mobile.index'))

        assert current_user.is_admin
        if not db_is_initialized():
            return redirect(url_for('admin.tourn'))

        tourn = TournInfo.get()
        tourn_name = session.get('tourn')
        if not tourn_name:
            # our session information has been cleared out somehow (should only happen in
            # testing)--let's just re-set it and log this as an event of interest
            session['tourn'] = tourn.name
            log.info(f"re-setting tourn = '{tourn.name}' in session state")

        view = active_view(tourn)
        return render_view(view)

    INVALID_ROUTE = "_INVALID"

    API_MAP = {
        "players/"    : "players/data",
        "seeding/"    : "seeding/data",
        "partners/"   : "partners/data",
        "teams/"      : "teams/data",
        "round_robin/": "round_robin/data",
        "final_four/" : "final_four/data",
        "playoffs/"   : "playoffs/data",
        "players"     : INVALID_ROUTE,
        "seeding"     : INVALID_ROUTE,
        "partners"    : INVALID_ROUTE,
        "teams"       : INVALID_ROUTE,
        "round_robin" : INVALID_ROUTE,
        "final_four"  : INVALID_ROUTE,
        "playoffs"    : INVALID_ROUTE
    }

    NO_DB_REQ = {
        'tourn/select_tourn'
    }

    @app.route("/api/<path:route>", methods=['GET', 'POST'])
    def api_router(route: str) -> str:
        """Reroute API calls.  The route handlers should treat these the same as calls
        from the app, except that only JSON data is returned (for errors, as well).  Note
        that the following request attributes will be different for API calls (we are not
        rewriting them here): `url`, `path`, `full_path`, and `endpoint`.
        """
        reroute = API_MAP.get(route) or route
        assert g.api_call  # consider this flag a framework thing
        # ATTN: `request_ctx` will be merged with `app_ctx` in Flask version 3.2, so the
        # URL adapter will move at that point!
        url_adapter = request_ctx.url_adapter
        endpoint, kwargs = url_adapter.match('/' + reroute, request.method)
        if endpoint not in current_app.view_functions:
            return render_error(404)
        if not db_is_initialized() and reroute not in NO_DB_REQ:
            return render_error(400, desc="No active tournament")
        view_func = current_app.view_functions[endpoint]
        return view_func(**kwargs)

    # end of `def create_app()`
    return app

#############
# renderers #
#############

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
    return render_response(LOGIN_TEMPLATE, **(base_ctx | context))

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
