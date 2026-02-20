# -*- coding: utf-8 -*-

"""Test team ranking process, including tie-breaking logic.
"""
import re

import pytest

from conftest import get_user_client

def test_index(client):
    """Sanity check, hitting '/' should return login page
    """
    resp = client.get('/', follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/login'
    assert "Select player..." in resp.text

def test_logins(seed_bracket_app):
    """Make sure disparate client sessions are independent of each other
    """
    app = seed_bracket_app
    crash_client = get_user_client(app, "Crash")
    resp = crash_client.get('/mobile/', follow_redirects=True)
    assert resp.status_code == 200
    assert re.search(r'User: <span.*>Crash</span>', resp.text)

    abs_client = get_user_client(app, "Abs")
    resp = abs_client.get('/mobile/', follow_redirects=True)
    assert resp.status_code == 200
    assert re.search(r'User: <span.*>Abs</span>', resp.text)

def test_post_score(seed_bracket_app):
    """Make sure disparate client sessions are independent of each other
    """
    app = seed_bracket_app
    virgilio_client = get_user_client(app, "Virgilio")
    resp = virgilio_client.get('/mobile/', follow_redirects=True)
    assert resp.status_code == 200
    assert re.search(r'User: <span.*>Virgilio</span>', resp.text)

    data = {'game_label'   : 'sd-1-1',
            'posted_by_num': '1',
            'team_idx'     : '0',
            'ref_score_id' : 'None',
            'team_pts'     : '10',
            'opp_pts'      : '0',
            'action'       : 'submit_score'}
    resp = virgilio_client.post('/mobile/seeding/submit_score', data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert re.search(r'<label>Score posted by</label>:.*<span>Virgilio \(you\)</span>',
                     resp.text, re.DOTALL)
