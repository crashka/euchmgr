# -*- coding: utf-8 -*-

"""Test mobile API.  As with the admin UI vs. API tests, we don't have to work too hard to
keep this module in sync with the mobile UI test module.  If the two diverge, it should be
for better coverage of areas more pertinent to their respective interfaces and/or clients.
"""

from collections.abc import Generator
import re
import json

import pytest
from peewee import SqliteDatabase
from flask import Flask
from flask.testing import FlaskClient

from conftest import TestConfig, MobileAPIAppProxy, MobileAPIClient, restore_stage_db
from database import db_is_initialized, db_reset
from schema import TournStage, TournInfo, clear_schema_cache
from server import create_app

############
# fixtures #
############

@pytest.fixture(scope="module")
def mobile_api_app() -> Generator[Flask]:
    """Class-level app instantiation.
    """
    app = create_app(TestConfig)
    app.wsgi_app = MobileAPIAppProxy(app.wsgi_app)
    app.testing = True
    yield app

@pytest.fixture(scope="class")
def mobile_api_client(mobile_api_app) -> Generator[FlaskClient]:
    """Class-level client instance.
    """
    app = mobile_api_app
    app.test_client_class = MobileAPIClient
    yield app.test_client()

@pytest.fixture(scope="class")
def register_db() -> Generator[SqliteDatabase]:
    """PLAYER_ROSTER"""
    db = restore_stage_db(TournStage(2))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture(scope="class")
def seeding_db() -> Generator[SqliteDatabase]:
    """SEED_BRACKET"""
    db = restore_stage_db(TournStage(4))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture(scope="class")
def partners_db() -> Generator[SqliteDatabase]:
    """PARTNER_PICK"""
    db = restore_stage_db(TournStage(8))
    yield db
    db_reset(force=True)
    clear_schema_cache()

################
# test classes #
################

class TestSanity:
    """
    """
    user: str = "Abs"

    def test_db(self, register_db):
        """
        """
        assert db_is_initialized()
        tourn = TournInfo.get()
        assert tourn.stage_compl == TournStage.PLAYER_ROSTER
    
    def test_login(self, mobile_api_client, register_db):
        """
        """
        client = mobile_api_client
        assert client.user is None
        assert client.login(self.user)
        assert client.user == self.user

    def test_logout(self, mobile_api_client, register_db):
        """
        """
        client = mobile_api_client
        assert client.user == self.user
        assert client.logout()
        assert client.user is None

class TestRegister:
    """
    """
    user1: str = "DiPesa"
    user2: str = "Latt"

    def test_register_view(self, mobile_api_client, register_db):
        """
        """
        client = mobile_api_client
        client.login(self.user1)
        resp = client.get("/register")
        assert resp.status_code == 200

        tourn = TournInfo.get()
        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']
        assert api_data['tourn']
        assert api_data['view']
