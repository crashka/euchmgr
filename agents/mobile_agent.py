#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Emulate a mobile client through the lifecycle of a tournament.
"""

from random import uniform, randrange
from time import sleep, time

from ckautils import typecast
from requests import Session, Response
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup, Tag

from core import config, profile, log

################
# module stuff #
################

cfg = config.config('mobile_agent', profile)

# update intervals status checks (in milliseconds)
UPD_INT = cfg['update_int']

# time to wait before client actions (in seconds)
WAIT_TIME = cfg['wait_time']

TIME_VAR = cfg['time_variance']

def wait_until(action_time: float, upd_cond: str) -> bool:
    """Wait (sleep) until the specified action time.  Returns boolean indicating whether
    the wait was interrupted by the auto-update timer.
    """
    wait_secs = action_time - time()
    upd_secs = UPD_INT[upd_cond] / 1000.0
    if wait_secs < 0:
        return False
    elif wait_secs < upd_secs:
        sleep(wait_secs)
        return False
    else:
        sleep(upd_secs)
        return True

def wait_for(action: str) -> None:
    """Wait (sleep) before the specified action, plus or minus variance (no interrupts).
    """
    mult = uniform(*TIME_VAR)
    wait_secs = WAIT_TIME[action] * mult
    sleep(wait_secs)

def action_time(action: str) -> float:
    """Return time when planned action should be taken (with variance added).
    """
    mult = uniform(*TIME_VAR)
    wait_secs = WAIT_TIME[action] * mult
    return time() + wait_secs

##################
# requests stuff #
##################

SERVER_ROOT = None

USER_AGENT = 'Mobile test agent'
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

def agent_post(path: str, data: dict = None) -> str:
    """Wrapper around POST request.
    """
    return sess.post(build_url(path), data=data)

def resp_error(resp: Response) -> str:
    """
    """
    soup = BeautifulSoup(resp.text, 'html.parser')
    err_msg = soup.select_one('h2')
    return err_msg.string

###############
# agent funcs #
###############

def login(user: str, pw: str = "") -> str:
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
    assert resp.request.path_url == '/mobile/seeding'

def active_view() -> tuple[str, BeautifulSoup]:
    """Get active view.  Return view path and parsed HTML.
    """
    resp = agent_get('/')
    assert resp.status_code == 200
    assert len(resp.history) == 2
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

def parse_teams(teams: list[Tag]) -> list[tuple[str, str]]:
    """Return list of tuples representing players names for the teams.
    """
    assert len(teams) == 2
    tm_players = []
    for team in teams:
        strings = list(team.stripped_strings)
        assert len(strings) == 5  # [num, plyr, '/', num, plyr]
        tm_players.append((strings[1], strings[4]))
    return tm_players

def parse_scores(score_block: Tag) -> tuple[int, int]:
    """Return tuple representing (team_pts, opp_pts).
    """
    scores = score_block.select('select')
    if len(scores) == 0:
        scores = score_block.select('span')
        score_val = lambda x: typecast(x.string)
    else:
        score_val = lambda x: typecast(x.select_one('option[selected]').string)

    assert len(scores) == 2
    # TODO: should really do this by team_pts/opp_pts and not assume the order!!!
    return tuple(score_val(score) for score in scores)

def seeding_agent(user: str, soup: BeautifulSoup) -> None:
    """Seeding agent loop.
    """
    while game := soup.select_one('section.games article.game.active'):
        form = soup.select_one('form[action="seeding"]')
        player_num = typecast(form.select_one('input[name="posted_by_num"]').get('value'))
        team_idx = typecast(form.select_one('input[name="team_idx"]').get('value'))
        ref_score_id = typecast(form.select_one('input[name="ref_score_id"]').get('value'))
        game_label = game['id']  # should be same as 'form input[name="game_label"]'
        teams = parse_teams(game.select('p.matchup span'))  # not currently used
        scores = parse_scores(game.select_one('p.score'))
        action_block = game.select_one('p.units + p')
        if not action_block.get('class'):
            # score successfully posted
            assert ref_score_id
            assert scores != (None, None)
            post_info = list(action_block.stripped_strings)
            assert len(post_info) == 3  # e.g. ['Score posted by', ':', 'Abs (you)']
            post_action = post_info[0].split(' ')[1]
            post_role = post_info[2].split(' ')[-1].strip('()')
            log.debug(f"active game: {post_info[0]} {post_info[2]}")

            new_soup = False
            upd_cond = 'compl_game' if post_action == 'accepted' else 'cur_game'
            accept_time = action_time('score_accept')
            while wait_until(accept_time, upd_cond):
                resp = agent_get(f"/mobile/game_score/{game_label}")
                assert len(resp.history) == 0
                if resp.status_code == 200:
                    data = resp.json()
                    post = data['data']
                    if post['id'] > ref_score_id:
                        log.debug(f"active game: new score posted")
                        resp = agent_get('/mobile/seeding/')
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        new_soup = True
                        break
                    elif post['do_push']:
                        log.debug(f"active game: score pushed")
                        resp = agent_get('/mobile/seeding')
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        new_soup = True
                        break
                    log.debug(f"active game: no new score post")
                    continue
                elif resp.status_code == 404:
                    log.debug(f"active game: score not yet posted")
                    data = resp.json()
                    post = data['data']  # for debugging
                    continue
                else:
                    raise RuntimeError(f"GET /game_score failed with status {resp.status_code}")
            if new_soup:
                continue

            # ready to accept score
            data = {'game_label'   : game_label,
                    'posted_by_num': player_num,
                    'team_idx'     : team_idx,
                    'ref_score_id' : ref_score_id,
                    'team_pts'     : scores[0],
                    'opp_pts'      : scores[1],
                    'action'       : 'accept_score'}
            resp = agent_post('/mobile/seeding/accept_score', data=data)
            assert resp.status_code == 200
            assert len(resp.history) == 2
            soup = BeautifulSoup(resp.text, 'html.parser')
        elif "actions" in action_block.get('class'):
            # no score posted yet
            assert not ref_score_id
            log.debug(f"active game: score not yet posted")

            new_soup = False
            submit_time = action_time('score_submit')
            while wait_until(submit_time, 'cur_game'):
                resp = agent_get(f"/mobile/game_score/{game_label}")
                assert len(resp.history) == 0
                if resp.status_code == 200:
                    data = resp.json()
                    post = data['data']
                    if post['id'] > ref_score_id:
                        log.debug(f"active game: new score posted")
                        resp = agent_get('/mobile/seeding/')
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        new_soup = True
                        break
                    elif post['do_push']:
                        log.debug(f"active game: score pushed")
                        resp = agent_get('/mobile/seeding')
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        new_soup = True
                        break
                    log.debug(f"active game: no new score post")
                    continue
                elif resp.status_code == 404:
                    log.debug(f"active game: score not yet posted")
                    data = resp.json()
                    post = data['data']  # for debugging
                    continue
                else:
                    raise RuntimeError(f"GET /game_score failed with status {resp.status_code}")
            if new_soup:
                continue

            # ready to submit score
            points = (10, randrange(10))
            if randrange(2) > 0:
                points = tuple(reversed(points))
            data = {'game_label'   : game_label,
                    'posted_by_num': player_num,
                    'team_idx'     : team_idx,
                    'ref_score_id' : '',
                    'team_pts'     : points[0],
                    'opp_pts'      : points[1],
                    'action'       : 'submit_score'}
            resp = agent_post('/mobile/seeding/submit_score', data=data)
            assert resp.status_code == 200
            assert len(resp.history) == 2
            soup = BeautifulSoup(resp.text, 'html.parser')
        else:
            raise RuntimeError("Unexpected element '{action_block}'")

    log.debug(f"seeding: no active game")
    return

VIEW_AGENTS = {
    '/mobile/seeding': seeding_agent
}

def mobile_agent() -> str:
    """Main loop for the mobile agent (must be logged in).
    """
    view, soup = active_view()
    user = soup.select_one('span.login_info span[title]').string

    done = False
    while not done:
        assert view in VIEW_AGENTS, f"No agent for view '{view}'"
        VIEW_AGENTS[view](user, soup)

        wait_for('check_view')
        view, soup = active_view()

########
# main #
########

import sys

from ckautils import parse_argv

def main() -> int:
    """Mobile client agent.

    Usage: python -m mobile_agent <server_url> <player_name> [<addl_args>]
    """
    usage = lambda x: x + "\n\n" + main.__doc__
    if len(sys.argv) < 2:
        return usage("Server URL not specified")
    if len(sys.argv) < 3:
        return usage("Player name not specified")

    server_url = sys.argv[1]
    player_name = sys.argv[2]
    args, kwargs = parse_argv(sys.argv[3:])  # pick up additional args

    set_server(server_url)
    login(player_name)
    mobile_agent()
    return 0

if __name__ == '__main__':
    sys.exit(main())
