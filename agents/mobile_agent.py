#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Emulate a mobile client through the lifecycle of a tournament.
"""

from functools import partial
from random import random, uniform, randrange, choice
from time import sleep, time
import re

from ckautils import typecast
from requests import Session, Response
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup, Tag

from core import config, profile, log, set_logger
from mobile import View

################
# module stuff #
################

cfg = config.config('mobile_agent', profile)

# update intervals status checks (in milliseconds)
UPD_INT = cfg['update_int']

# time to wait before client actions (in seconds)
WAIT_TIME = cfg['wait_time']

TIME_VAR = cfg['time_variance']

def wait_until(action_time: float | None, upd_cond: str) -> bool:
    """Wait (sleep) until the specified action time.  Returns boolean indicating whether
    the wait was interrupted by the auto-update timer.  If action time is specified as
    empty, then only consider the update interval (as interrupting a forever wait).
    """
    upd_secs = UPD_INT[upd_cond] / 1000.0
    if not action_time:
        sleep(upd_secs)
        return True

    wait_secs = action_time - time()
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

def action_time(action: str | None) -> float | None:
    """Return time when planned action should be taken (with variance added).  Supports
    null actions (return value will be interpreted downstream as "no target time").
    """
    if not action:
        return None
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
    # FIX: need to parse some useful information out of `resp.text` rather than return the
    # full HTML!!!
    return err_msg.string if err_msg else resp.text

###############
# agent funcs #
###############

def login(user: str, pw: str = "") -> tuple[str, BeautifulSoup]:
    """Log in the user, and render the active view.
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
    """Render the active view.  Return view path and parsed HTML.
    """
    resp = agent_get('/')
    assert resp.status_code == 200
    assert len(resp.history) == 2
    soup = BeautifulSoup(resp.text, 'html.parser')
    return resp.request.path_url, soup

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

def get_view_status(parent: Tag) -> str | None:
    """Look for the "Status" field in the view info section and return the text value.
    """
    info_sect = parent.select_one('section.info_stats')
    # the first status field (if multiple) represents the status of the stage (as opposed
    # to the player, e.g. in the case of the /register view)
    stat_lbl = info_sect.find('label', string=re.compile(r'^Status'))
    stat_fld = stat_lbl.find_next_sibling('span')
    return stat_fld.string if stat_fld else None

def game_view_agent(soup: BeautifulSoup, view: View = None) -> None:
    """View agent for game playing stages.
    """
    assert view is not None
    view_path = f'/mobile/{view}'
    action_url = lambda action: f'/mobile/{view}/{action}'

    # it is assumed that we have new soup on every loop (it would nice to be able to
    # assert this!)
    while game := soup.select_one('section.games article.game.active'):
        form = soup.select_one(f'form[action="{view}"]')
        player_num = typecast(form.select_one('input[name="posted_by_num"]').get('value'))
        team_idx = typecast(form.select_one('input[name="team_idx"]').get('value'))
        ref_score_id = typecast(form.select_one('input[name="ref_score_id"]').get('value')) or 0
        game_label = game['id']  # should be same as 'form input[name="game_label"]'
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
            log.debug(f"active game {game_label}: {post_info[0]} {post_info[2]}")

            new_soup = None
            # decide on whether we plan on correcting, accepting, or neither (though we
            # may get interrupted before actually executing)
            action = None
            if random() < cfg['correct_score_freq']:
                # note that anyone may correct a score, including "you"
                action = 'correct_score'
            elif post_role == 'opponent':
                action = 'accept_score'
            upd_cond = 'compl_game' if post_action == 'accepted' else 'cur_game'
            act_target = action_time(action)  # a forever wait, if no action assigned
            while wait_until(act_target, upd_cond):
                resp = agent_get(f"/mobile/game_score/{game_label}")
                assert len(resp.history) == 0
                if resp.status_code == 200:
                    data = resp.json()
                    post = data['data']
                    if post['id'] > ref_score_id:
                        log.debug(f"active game {game_label}: new score posted (id {post['id']})")
                        resp = agent_get(view_path + '/')
                        new_soup = BeautifulSoup(resp.text, 'html.parser')
                        break
                    elif post['do_push']:
                        log.debug(f"active game {game_label}: score pushed")
                        resp = agent_get(view_path)
                        new_soup = BeautifulSoup(resp.text, 'html.parser')
                        break
                    log.debug(f"active game {game_label}: no new score post")
                    continue
                elif resp.status_code == 404:
                    log.debug(f"active game {game_label}: score not yet posted")
                    data = resp.json()
                    post = data['data']  # for debugging
                    continue
                else:
                    raise RuntimeError(f"GET /game_score failed with status {resp.status_code}")
            if new_soup:
                soup = new_soup
                if err_msg := soup.select_one('span.err_msg').string:
                    log.debug(f"active game {game_label}: err_msg '{err_msg}'")
                continue

            # ready to correct or accept score
            if action == 'correct_score':
                points = (10, randrange(10))
                if randrange(2) > 0:
                    points = tuple(reversed(points))
                if points == scores:
                    points = tuple(reversed(points))
                scores = points
            data = {'game_label'   : game_label,
                    'posted_by_num': player_num,
                    'team_idx'     : team_idx,
                    'ref_score_id' : ref_score_id,
                    'team_pts'     : scores[0],
                    'opp_pts'      : scores[1],
                    'action'       : action}
            resp = agent_post(action_url(action), data=data)
            assert resp.status_code == 200
            assert len(resp.history) == 2
            soup = BeautifulSoup(resp.text, 'html.parser')
            if err_msg := soup.select_one('span.err_msg').string:
                log.debug(f"active game {game_label}: err_msg '{err_msg}'")
        elif "actions" in action_block.get('class'):
            # no score posted yet
            assert not ref_score_id
            log.debug(f"active game {game_label}: score not yet posted")

            new_soup = None
            action = 'submit_score'
            upd_cond = 'cur_game'
            act_target = action_time(action)
            while wait_until(act_target, upd_cond):
                resp = agent_get(f"/mobile/game_score/{game_label}")
                assert len(resp.history) == 0
                if resp.status_code == 200:
                    data = resp.json()
                    post = data['data']
                    if post['id'] > ref_score_id:
                        log.debug(f"active game {game_label}: new score posted (id {post['id']})")
                        resp = agent_get(view_path + '/')
                        new_soup = BeautifulSoup(resp.text, 'html.parser')
                        break
                    elif post['do_push']:
                        log.debug(f"active game {game_label}: score pushed")
                        resp = agent_get(view_path)
                        new_soup = BeautifulSoup(resp.text, 'html.parser')
                        break
                    log.debug(f"active game {game_label}: no new score post")
                    continue
                elif resp.status_code == 404:
                    log.debug(f"active game {game_label}: score not yet posted")
                    data = resp.json()
                    post = data['data']  # for debugging
                    continue
                else:
                    raise RuntimeError(f"GET /game_score failed with status {resp.status_code}")
            if new_soup:
                soup = new_soup
                if err_msg := soup.select_one('span.err_msg').string:
                    log.debug(f"active game {game_label}: err_msg '{err_msg}'")
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
                    'action'       : action}
            resp = agent_post(action_url(action), data=data)
            assert resp.status_code == 200
            assert len(resp.history) == 2
            soup = BeautifulSoup(resp.text, 'html.parser')
            if err_msg := soup.select_one('span.err_msg').string:
                log.debug(f"active game {game_label}: err_msg '{err_msg}'")
        else:
            raise RuntimeError("Unexpected element '{action_block}'")

    log.debug(f"{view}: no active game")
    return

def partners_view_agent(soup: BeautifulSoup) -> None:
    """Round robin agent loop.
    """
    view = View.PARTNERS
    view_path = f'/mobile/{view}'
    action_url = lambda action: f'/mobile/{view}/{action}'

    # it is assumed that we have new soup on every loop (it would nice to be able to
    # assert this!)
    while pick := soup.select_one('article.pick.active'):
        form = soup.select_one(f'form[action="{view}"]')
        player_num = typecast(form.select_one('input[name="player_num"]').get('value'))
        cur_pick_id = typecast(form.select_one('input[name="cur_pick_id"]').get('value')) or 0
        if partner_sel := pick.select_one('span.partner select[name="partner_num"]'):
            # it's our pick
            avail = partner_sel.select('option:not([disabled])')
            partner_num = typecast(choice(avail).get('value'))
            picks_info = pick.select_one('input[name="picks_info"]').get('value')
            action = 'pick_partner'
            wait_for(action)
            data = {'player_num'   : player_num,
                    'partner_num'  : partner_num,
                    'picks_info'   : picks_info,
                    'action'       : action}
            resp = agent_post(action_url(action), data=data)
            assert resp.status_code == 200
            assert len(resp.history) == 2
            soup = BeautifulSoup(resp.text, 'html.parser')
            if err_msg := soup.select_one('span.err_msg').string:
                log.debug(f"active pick num {player_num}: err_msg '{err_msg}'")
            continue

        # not our pick, we just wait until something happens
        new_soup = None
        while wait_until(None, 'cur_pick'):
            resp = agent_get("/mobile/current_pick")
            assert len(resp.history) == 0
            if resp.status_code == 200:
                data = resp.json()
                pick = data['data']
                if not pick:
                    log.debug(f"active pick num {player_num}: done picking")
                    resp = agent_get(view_path)
                    new_soup = BeautifulSoup(resp.text, 'html.parser')
                    break
                elif pick['id'] != cur_pick_id:
                    log.debug(f"active pick num {player_num}: new pick posted (id {pick['id']})")
                    resp = agent_get(view_path + '/')
                    new_soup = BeautifulSoup(resp.text, 'html.parser')
                    break
                log.debug(f"active pick num {player_num}: no new pick posted")
                continue
            else:
                raise RuntimeError(f"GET /current_pick failed with status {resp.status_code}")
        if new_soup:
            soup = new_soup
            if err_msg := soup.select_one('span.err_msg').string:
                log.debug(f"active game {game_label}: err_msg '{err_msg}'")
            continue
        assert False, "NOTREACHED"

    log.debug(f"{view}: no active pick")
    return

VIEW_AGENTS = {
    '/mobile/seeding'    : partial(game_view_agent, view=View.SEEDING),
    '/mobile/partners'   : partners_view_agent,
    '/mobile/round_robin': partial(game_view_agent, view=View.ROUND_ROBIN),
    '/mobile/semifinals' : partial(game_view_agent, view=View.SEMIFINALS),
    '/mobile/finals'     : partial(game_view_agent, view=View.FINALS)
}

def mobile_agent(player_name: str) -> str:
    """Setup and main loop for the mobile agent.
    """
    view, soup = login(player_name)
    assert view in VIEW_AGENTS, f"No agent for view '{view}'"
    log.debug(f"view {view}, status '{get_view_status(soup)}'")
    user = soup.select_one('span.login_info span[title]').string

    done = False
    while not done:
        VIEW_AGENTS[view](soup)
        wait_for('check_view')
        view, soup = active_view()
        assert view in VIEW_AGENTS, f"No agent for view '{view}'"
        log.debug(f"view {view}, status '{get_view_status(soup)}'")

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

    player_tag = player_name.translate({ord("'"): "", ord(" "): ""}).lower()
    log_name = f"agent-{player_tag}"
    set_logger(log_name)
    set_server(server_url)
    mobile_agent(player_name)
    return 0

if __name__ == '__main__':
    sys.exit(main())
