# -*- coding: utf-8 -*-

"""Test mobile UI.
"""

from collections.abc import Generator
import re

import pytest
from peewee import SqliteDatabase
from flask import Flask
from flask.testing import FlaskClient

from conftest import TestConfig, MobileAppProxy, restore_stage_db
from database import db_reset
from schema import TournStage, clear_schema_cache
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
    assert "Select player..." in resp.text

def test_logins(seed_bracket_app):
    """Make sure disparate client sessions are independent of each other.
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
    """Test basic submitting of game score.
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
