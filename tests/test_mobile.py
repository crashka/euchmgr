# -*- coding: utf-8 -*-

"""Test team ranking process, including tie-breaking logic.
"""
from collections.abc import Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from server import Config, create_app

################
# client proxy #
################

TEST_USER_AGENT = "Mobile test client"

class FlaskTestClientProxy(object):
    """From https://stackoverflow.com/q/15278285
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['HTTP_USER_AGENT'] = TEST_USER_AGENT
        return self.app(environ, start_response)

##########
# config #
##########

class TestConfig(Config):
    """Subclass the default flask app config
    """
    pass

############
# fixtures #
############

@pytest.fixture(scope="module")
def app(seed_bracket_db) -> Generator[Flask]:
    """Module-level app instantiation (caches database reference)
    """
    app = create_app(TestConfig)
    app.wsgi_app = FlaskTestClientProxy(app.wsgi_app)
    app.testing = True
    yield app

@pytest.fixture()
def client(app):
    """Unauthenticated client instance
    """
    yield app.test_client()

def get_user_client(app: Flask, user: str) -> FlaskClient:
    """Fake fixture, return authenticated client instance
    """
    client = app.test_client()
    client.post("/login", data={'username': user}, follow_redirects=True)
    return client

#########
# tests #
#########

def test_index(client):
    """Sanity check, hitting '/' should return login page
    """
    response = client.get('/', follow_redirects=True)
    assert response.status_code == 200
    assert len(response.history) == 1
    assert response.request.path == '/login'
    assert "Select player..." in response.text

def test_logins(app):
    """Make sure disparate client sessions are independent of each other
    """
    crash_client = get_user_client(app, "Crash")
    response = crash_client.get('/mobile', follow_redirects=True)
    assert response.status_code == 200
    assert "Logged in as: <span>Crash</span>" in response.text

    abs_client = get_user_client(app, "Abs")
    response = abs_client.get('/mobile', follow_redirects=True)
    assert response.status_code == 200
    assert "Logged in as: <span>Abs</span>" in response.text
