#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Emulate an admin client through the lifecycle of a tournament.
"""

from os import environ
from functools import partial
from random import uniform
from time import sleep, time

from ckautils import typecast
from requests import Session, Response
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup, Tag

from core import config, profile, log, set_logger
from security import ADMIN_USER
from admin import View, SEL_NEW

################
# module stuff #
################

cfg = config.config('admin_agent', profile)

# reload interval for view data (in milliseconds)
RELOAD_INT = cfg['reload_int']

# time to wait before admin actions (by view, in seconds)
WAIT_TIME = cfg['wait_time']

TIME_VAR = cfg['time_variance']

def wait_for(action: str) -> None:
    """Wait (sleep) before specified action (or action type), plus or minus variance.
    """
    mult = uniform(*TIME_VAR)
    wait_secs = WAIT_TIME[action] * mult
    sleep(wait_secs)

def validate_button(parent: Tag, btn_value: str, enabled: bool) -> None:
    """Validate state of button.
    """
    assert parent
    selector = f'button[value="{btn_value}"]'
    assert parent.select_one(selector)
    assert parent.select_one(selector).get('disabled') == (None if enabled else '')

##################
# requests stuff #
##################

SERVER_ROOT = None

USER_AGENT = 'Admin test agent'
headers = {'user-agent': USER_AGENT}

sess = Session()
sess.headers.update(headers)
#sess.cert = '/var/certs/cert.pem'
sess.verify = False

urllib3.disable_warnings(InsecureRequestWarning)

def set_server(server_root: str) -> None:
    """Set server root URL (currently no validation).
    """
    global SERVER_ROOT
    SERVER_ROOT = server_root

def build_url(path: str) -> str:
    """Build full URL for the specified path
    """
    return SERVER_ROOT + path

def agent_get(path: str) -> str:
    """Wrapper around GET request.
    """
    return sess.get(build_url(path))

def agent_post(path: str, data: dict = None, files: dict = None) -> str:
    """Wrapper around POST request.
    """
    return sess.post(build_url(path), data=data, files=files)

def resp_error(resp: Response) -> str:
    """
    """
    soup = BeautifulSoup(resp.text, 'html.parser')
    err_msg = soup.select_one('h2')
    return err_msg.string if err_msg else resp.text

###############
# agent funcs #
###############

def login(user: str, pw: str = "") -> tuple[str, BeautifulSoup]:
    """Returns active view.
    """
    resp = agent_get('/')
    if resp.status_code != 200:
        err_msg = resp_error(resp)
        raise RuntimeError(f"Login failed with status {resp.status_code}: {err_msg}")
    assert len(resp.history) == 1
    assert resp.request.path_url == '/login'

    data = {'username': user, 'password': pw}
    resp = agent_post("/login", data=data)
    assert resp.status_code == 200
    assert len(resp.history) == 2
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def active_view() -> tuple[str, BeautifulSoup]:
    """Get active view.  Return view path and parsed HTML.
    """
    resp = agent_get('/')
    assert resp.status_code == 200
    assert len(resp.history) == 1
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def render_view(view:str) -> tuple[str, BeautifulSoup]:
    """Render the specified view (validate the resultant path).
    """
    view_path = f"/{view}"
    resp = agent_get(view_path)
    assert resp.status_code == 200
    assert len(resp.history) == 0
    assert resp.request.path_url == view_path
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def select_new() -> tuple[str, BeautifulSoup]:
    """Setup step for creating a new tournament.  Implicitly pauses the active tournament,
    if any (not checked here).
    """
    data = {
        'action': "select_tourn",
        'tourn' : SEL_NEW
    }
    resp = agent_post("/tourn/select_tourn", data=data)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def create_tourn(tourn_name: str, roster_file: str = None) -> tuple[str, BeautifulSoup]:
    """Create specified tournament.  Canonical roster file name is used, if not passed in.
    """
    view, soup = select_new() 
    assert view == '/tourn'
    data = {
        'action'     : 'create_tourn',
        'tourn_id'   : '',
        'tourn_name' : tourn_name,
        'overwrite'  : 'yes'
    }
    roster_file = roster_file or f"{tourn_name}_roster.csv"
    files = {
        'roster_file': (roster_file, open(roster_file, "rb")),
    }
    resp = agent_post("/tourn/create_tourn", data=data, files=files)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path_url == '/players'
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def select_tourn(tourn_name: str) -> tuple[str, BeautifulSoup]:
    """Select specified tournament (from /tourn view).  Implicitly pauses the action
    tournament, if any (not checked here).
    """
    data = {
        'action': "select_tourn",
        'tourn' : tourn_name
    }
    resp = agent_post("/tourn/select_tourn", data=data)
    assert resp.status_code == 200
    assert len(resp.history) == 2
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def tourn_view_agent(soup: BeautifulSoup) -> None:
    """Tournament management agent.
    """
    raise NotImplementedError("Agent for /tourn view not (yet?) implemented")

def players_view_agent(soup: BeautifulSoup) -> tuple[str, BeautifulSoup]:
    """Players view agent.
    """
    # validate view
    form = soup.select_one('form.actions[action="players"]')
    validate_button(form, "gen_player_nums", True)
    validate_button(form, "gen_seed_bracket", False)

    # generate player nums
    wait_for('players_actn')
    data = {
        'action': "gen_player_nums"
    }
    resp = agent_post("/players/gen_player_nums", data=data)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path_url == '/players'
    soup = BeautifulSoup(resp.text, 'html.parser')

    # validate updated view
    form = soup.select_one('form.actions[action="players"]')
    validate_button(form, "gen_player_nums", False)
    validate_button(form, "gen_seed_bracket", True)

    # create seeding bracket
    wait_for('players_actn')
    data = {
        'action': "gen_seed_bracket"
    }
    resp = agent_post("/players/gen_seed_bracket", data=data)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path_url == '/seeding'
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def partners_view_agent(soup: BeautifulSoup) -> None:
    """Partners view agent.
    """
    raise NotImplementedError("Agent for /partners view not (yet?) implemented")

def teams_view_agent(soup: BeautifulSoup) -> None:
    """Teams view agent.
    """
    raise NotImplementedError("Agent for /teams view not (yet?) implemented")

def final_four_view_agent(soup: BeautifulSoup) -> None:
    """Final Four view agent.
    """
    raise NotImplementedError("Agent for /final_four view not (yet?) implemented")

def game_view_agent(soup: BeautifulSoup, view: View = None) -> None:
    """View agent for game playing stages.
    """
    assert view is not None
    raise NotImplementedError("Agent for game views not (yet?) implemented")
    # TODO:
    #   - break this up into separate agents for each view!
    #   - start all live charts/dashboards (using subprocess.Popen)
    #   - loop until all buttons have been pressed
    #   - terminate child charts/dashboards before returning

VIEW_AGENTS = {
    '/tourn'      : tourn_view_agent,
    '/players'    : players_view_agent,
    '/seeding'    : partial(game_view_agent, view=View.SEEDING),
    '/partners'   : partners_view_agent,
    '/teams'      : teams_view_agent,
    '/round_robin': partial(game_view_agent, view=View.ROUND_ROBIN),
    '/final_four' : final_four_view_agent,
    '/playoffs'   : partial(game_view_agent, view=View.PLAYOFFS)
}

def admin_agent(tourn_name: str, **kwargs) -> str:
    """Setup and main loop for the admin agent (must be logged in).
    """
    view, soup = login("admin", ADMIN_PW)
    assert view in VIEW_AGENTS, f"No agent for view '{view}'"
    user = soup.select_one('span.login_info span[title]').string
    assert user == ADMIN_USER

    if view != '/tourn':
        view, soup = render_view('/tourn')

    if kwargs.get('create_new', False):
        view, soup = create_tourn(tourn_name, kwargs.get('roster_file'))
    else:
        view, soup = select_tourn(tourn_name)

    # now start the main agent loop
    done = False
    while not done:
        VIEW_AGENTS[view](soup)
        wait_for('check_view')
        view, soup = active_view()
        assert view in VIEW_AGENTS, f"No agent for view '{view}'"

########
# main #
########

import sys

from ckautils import parse_argv

ADMIN_PW = environ.get('EUCHMGR_ADMIN_PW')
assert ADMIN_PW, "EUCHMGR_ADMIN_PW must be set in the env"

LOGGER_NAME = "agent-admin"

def main() -> int:
    """Admin client agent.

    Usage: python -m admin_agent <server_url> <tourn_name> [<addl_args>]

    Additional arguments:
    - create_new=<boolean>     [defaults to false]
    - roster_file=<file name>  [defaults to <tourn_name>_roster.csv]

    Note that the admin password should be passed in using the EUCHMGR_ADMIN_PW
    environment variable.
    """
    usage = lambda x: x + "\n\n" + main.__doc__
    if len(sys.argv) < 2:
        return usage("Server URL not specified")
    if len(sys.argv) < 3:
        return usage("Tournament name not specified")

    server_url = sys.argv[1]
    tourn_name = sys.argv[2]
    args, kwargs = parse_argv(sys.argv[3:])  # pick up additional args
    if args:
        return usage(f"unexpected args: {args}")

    set_logger(LOGGER_NAME)
    set_server(server_url)
    admin_agent(tourn_name, **kwargs)
    return 0

if __name__ == '__main__':
    sys.exit(main())
