# -*- coding: utf-8 -*-

"""Common constants, fixtures, etc.
"""
from collections.abc import Generator
import shutil

import pytest
from peewee import SqliteDatabase
from flask import Flask
from flask.testing import FlaskClient

from core import TEST_DIR
from database import db_filepath, db_init, db_close
from schema import TournStage, clear_schema_cache
from server import Config, create_app

##################
# database stuff #
##################

TEST_DB = "test"

def stage_db_path(stage_num: int) -> str:
    """Build full pathname for stage-level database snapshot.
    """
    name = f"{TEST_DB}-stage-{stage_num}"
    return db_filepath(name, TEST_DIR)

def save_stage_db(stage: TournStage) -> SqliteDatabase:
    """Create snapshot of current database tagged with the specified stage.

    NOTE: we should really push the actual ORM call back into the `database` module!!!
    """
    db = db_close()  # checkpoint the WAL (idempotent)
    db.backup_to_file(stage_db_path(stage))
    return db

def restore_stage_db(stage: TournStage) -> SqliteDatabase:
    """Opposite of `save_stage_db` (same as above on encapsulating the low-level ORM
    knowledge).
    """
    db = db_close()  # checkpoint the WAL (idempotent)
    # REVISIT: it might be better (i.e. more robust if open connections on TEST_DB) to use
    # `db.backup` here!!!
    shutil.copy2(stage_db_path(stage), db_filepath(TEST_DB))
    db = db_init(TEST_DB, force=True)
    return db

@pytest.fixture
def stage_1_db() -> Generator[SqliteDatabase]:
    """TOURN_CREATE"""
    db = restore_stage_db(TournStage(1))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_2_db() -> Generator[SqliteDatabase]:
    """PLAYER_ROSTER"""
    db = restore_stage_db(TournStage(2))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_3_db() -> Generator[SqliteDatabase]:
    """PLAYER_NUMS"""
    db = restore_stage_db(TournStage(3))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_4_db() -> Generator[SqliteDatabase]:
    """SEED_BRACKET"""
    db = restore_stage_db(TournStage(4))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_5_db() -> Generator[SqliteDatabase]:
    """SEED_RESULTS"""
    db = restore_stage_db(TournStage(5))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_6_db() -> Generator[SqliteDatabase]:
    """SEED_TABULATE"""
    db = restore_stage_db(TournStage(6))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_7_db() -> Generator[SqliteDatabase]:
    """SEED_RANKS"""
    db = restore_stage_db(TournStage(7))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_8_db() -> Generator[SqliteDatabase]:
    """PARTNER_PICK"""
    db = restore_stage_db(TournStage(8))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_9_db() -> Generator[SqliteDatabase]:
    """TOURN_TEAMS"""
    db = restore_stage_db(TournStage(9))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_10_db() -> Generator[SqliteDatabase]:
    """TEAM_SEEDS"""
    db = restore_stage_db(TournStage(10))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_11_db() -> Generator[SqliteDatabase]:
    """TOURN_BRACKET"""
    db = restore_stage_db(TournStage(11))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_12_db() -> Generator[SqliteDatabase]:
    """TOURN_RESULTS"""
    db = restore_stage_db(TournStage(12))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_13_db() -> Generator[SqliteDatabase]:
    """TOURN_TABULATE"""
    db = restore_stage_db(TournStage(13))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def stage_14_db() -> Generator[SqliteDatabase]:
    """TEAMS_RANKS"""
    db = restore_stage_db(TournStage(14))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture
def test_db() -> Generator[SqliteDatabase]:
    """Note that the yield value for this function can easily be ignored (e.g. we can use
    this with the `usefixtures` marker).
    """
    db = db_init(TEST_DB, force=True)
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture(scope="module")
def seed_bracket_db() -> Generator[SqliteDatabase]:
    """SEED_BRACKET"""
    db = restore_stage_db(TournStage(4))
    yield db
    db_close()
    clear_schema_cache()

@pytest.fixture(scope="module")
def tourn_bracket_db() -> Generator[SqliteDatabase]:
    """TOURN_BRACKET"""
    db = restore_stage_db(TournStage(11))
    yield db
    db_close()
    clear_schema_cache()

################
# mobile stuff #
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

class TestConfig(Config):
    """Subclass the default flask app config
    """
    pass

@pytest.fixture(scope="module")
def seed_bracket_app(seed_bracket_db) -> Generator[Flask]:
    """Module-level app instantiation (caches database reference)
    """
    app = create_app(TestConfig)
    app.wsgi_app = FlaskTestClientProxy(app.wsgi_app)
    app.testing = True
    yield app

@pytest.fixture(scope="module")
def tourn_bracket_app(tourn_bracket_db) -> Generator[Flask]:
    """Module-level app instantiation (caches database reference)
    """
    app = create_app(TestConfig)
    app.wsgi_app = FlaskTestClientProxy(app.wsgi_app)
    app.testing = True
    yield app

@pytest.fixture()
def client(seed_bracket_app):
    """Unauthenticated client instance
    """
    app = seed_bracket_app
    yield app.test_client()

def get_user_client(app: Flask, user: str, pw: str = "") -> FlaskClient:
    """Fake fixture, return authenticated client instance
    """
    data = {'username': user, 'password': pw}
    client = app.test_client()
    client.post("/login", data=data, follow_redirects=True)
    return client
