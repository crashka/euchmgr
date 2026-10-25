# -*- coding: utf-8 -*-

"""Test mobile UI.
"""

from collections.abc import Generator
import re

import pytest
from peewee import SqliteDatabase
from flask import Flask
from flask.testing import FlaskClient
from bs4 import BeautifulSoup

from conftest import TestConfig, MobileAppProxy, restore_stage_db
from database import db_reset
from schema import TournInfo, TournStage, clear_schema_cache
from server import create_app

############
# fixtures #
############

@pytest.fixture(scope="module")
def seed_bracket_db() -> Generator[SqliteDatabase]:
    """SEED_BRACKET"""
    db = restore_stage_db(TournStage(4))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture(scope="module")
def tourn_bracket_db() -> Generator[SqliteDatabase]:
    """TOURN_BRACKET"""
    db = restore_stage_db(TournStage(11))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture(scope="module")
def seed_bracket_app(seed_bracket_db) -> Generator[Flask]:
    """Module-level app instantiation (caches database reference)
    """
    app = create_app(TestConfig)
    app.wsgi_app = MobileAppProxy(app.wsgi_app)
    app.testing = True
    yield app

@pytest.fixture(scope="module")
def tourn_bracket_app(tourn_bracket_db) -> Generator[Flask]:
    """Module-level app instantiation (caches database reference)
    """
    app = create_app(TestConfig)
    app.wsgi_app = MobileAppProxy(app.wsgi_app)
    app.testing = True
    yield app

@pytest.fixture
def mobile_client(seed_bracket_app) -> Generator[FlaskClient]:
    """Test-level client instance.
    """
    app = seed_bracket_app
    yield app.test_client()

def get_user_client(app: Flask, user: str, pw: str = "") -> FlaskClient:
    """Fake fixture, return authenticated client instance.
    """
    data = {'username': user, 'password': pw}
    client = app.test_client()
    client.post("/login", data=data, follow_redirects=True)
    return client

#########
# tests #
#########

# TODO: reorganize into test classes!!!

def test_index(mobile_client):
    """Sanity check, hitting '/' should return login page.
    """
    client = mobile_client
    resp = client.get('/', follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/login'

    soup = BeautifulSoup(resp.text, 'html.parser')
    form = soup.select_one('form[action="/login"]')
    assert form
    select = form.select_one('select[name="username"]')
    assert select
    options = select.select('option')
    tourn = TournInfo.get()
    assert len(options) == tourn.players + 1
    assert options[0].get('value') == ''
    assert options[0].get('selected') == ''
    assert options[0].string == "Select player..."

def test_logins(seed_bracket_app):
    """Make sure disparate client sessions are independent of each other.
    """
    app = seed_bracket_app
    crash_client = get_user_client(app, "Crash")
    resp = crash_client.get('/mobile/', follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/mobile/seeding'

    soup = BeautifulSoup(resp.text, 'html.parser')
    user_span = soup.select_one('span.login_info span[title]')
    user_span.string == "Crash"

    abs_client = get_user_client(app, "Abs")
    resp = abs_client.get('/mobile/', follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/mobile/seeding'

    soup = BeautifulSoup(resp.text, 'html.parser')
    user_span = soup.select_one('span.login_info span[title]')
    user_span.string == "Abs"

def test_post_score(seed_bracket_app):
    """Test basic submitting of game score.
    """
    app = seed_bracket_app
    virgilio_client = get_user_client(app, "Virgilio")
    resp = virgilio_client.get('/mobile/', follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/mobile/seeding'

    soup = BeautifulSoup(resp.text, 'html.parser')
    user_span = soup.select_one('span.login_info span[title]')
    user_span.string == "Virgilio"

    game = soup.select_one('section.games article.game.active')
    game_label = game['id']
    post_info = game.select_one('p.units + p')
    assert post_info and "actions" in post_info.get('class')

    data = {'game_label'   : game_label,
            'posted_by_num': '1',
            'team_idx'     : '0',
            'ref_score_id' : 'None',
            'team_pts'     : '10',
            'opp_pts'      : '0',
            'action'       : 'submit_score'}
    resp = virgilio_client.post('/mobile/seeding/submit_score', data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 2
    assert resp.request.path == '/mobile/seeding'

    soup = BeautifulSoup(resp.text, 'html.parser')
    game = soup.select_one('section.games article.game')
    assert game['id'] == game_label
    post_info = game.select_one('p.units + p')
    assert post_info and not post_info.get('class')
    assert ''.join(post_info.stripped_strings) == "Score posted by:Virgilio (you)"
