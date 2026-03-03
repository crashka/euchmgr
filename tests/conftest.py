# -*- coding: utf-8 -*-

"""Common constants, fixtures, ..., other stuff
"""

from collections.abc import Generator
import shutil
import json

import pytest
from peewee import SqliteDatabase
from flask.testing import FlaskClient

from core import TEST_DIR, DataFile
from database import db_filepath, db_init, db_reset, db_close
from schema import TournStage, clear_schema_cache
from server import Config

######################
# database utilities #
######################

TEST_DB = "test"
ROSTER_FILE = DataFile("test_roster.csv", TEST_DIR)
RAND_SEEDS = list(x * 10 for x in range(10))

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
    db_reset(force=True)
    clear_schema_cache()
    # REVISIT: it might be better (i.e. more robust if open connections on TEST_DB) to use
    # `db.backup` here!!!
    shutil.copy2(stage_db_path(stage), db_filepath(TEST_DB))
    db = db_init(TEST_DB, force=True)
    return db

#####################
# database fixtures #
#####################

@pytest.fixture
def stage_1_db() -> Generator[SqliteDatabase]:
    """TOURN_CREATE"""
    db = restore_stage_db(TournStage(1))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_2_db() -> Generator[SqliteDatabase]:
    """PLAYER_ROSTER"""
    db = restore_stage_db(TournStage(2))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_3_db() -> Generator[SqliteDatabase]:
    """PLAYER_NUMS"""
    db = restore_stage_db(TournStage(3))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_4_db() -> Generator[SqliteDatabase]:
    """SEED_BRACKET"""
    db = restore_stage_db(TournStage(4))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_5_db() -> Generator[SqliteDatabase]:
    """SEED_RESULTS"""
    db = restore_stage_db(TournStage(5))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_6_db() -> Generator[SqliteDatabase]:
    """SEED_TABULATE"""
    db = restore_stage_db(TournStage(6))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_7_db() -> Generator[SqliteDatabase]:
    """SEED_RANKS"""
    db = restore_stage_db(TournStage(7))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_8_db() -> Generator[SqliteDatabase]:
    """PARTNER_PICK"""
    db = restore_stage_db(TournStage(8))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_9_db() -> Generator[SqliteDatabase]:
    """TOURN_TEAMS"""
    db = restore_stage_db(TournStage(9))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_10_db() -> Generator[SqliteDatabase]:
    """TEAM_SEEDS"""
    db = restore_stage_db(TournStage(10))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_11_db() -> Generator[SqliteDatabase]:
    """TOURN_BRACKET"""
    db = restore_stage_db(TournStage(11))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_12_db() -> Generator[SqliteDatabase]:
    """TOURN_RESULTS"""
    db = restore_stage_db(TournStage(12))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_13_db() -> Generator[SqliteDatabase]:
    """TOURN_TABULATE"""
    db = restore_stage_db(TournStage(13))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture
def stage_14_db() -> Generator[SqliteDatabase]:
    """TEAMS_RANKS"""
    db = restore_stage_db(TournStage(14))
    yield db
    db_reset(force=True)
    clear_schema_cache()

###################
# common UI stuff #
###################

class TestConfig(Config):
    """Subclass the default flask app config.
    """
    DEBUG = True

################
# mobile stuff #
################

MOBILE_USER_AGENT = "Mobile test client"

class MobileAppProxy:
    """From https://stackoverflow.com/q/15278285.
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['HTTP_USER_AGENT'] = MOBILE_USER_AGENT
        return self.app(environ, start_response)

###############
# admin stuff #
###############

ADMIN_USER_AGENT = "Admin test client"

class AdminAppProxy:
    """From https://stackoverflow.com/q/15278285.
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['HTTP_USER_AGENT'] = ADMIN_USER_AGENT
        return self.app(environ, start_response)

#############
# API stuff #
#############

API_USER_AGENT = "Admin API test client"

class APIAppProxy:
    """From https://stackoverflow.com/q/15278285.
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['HTTP_USER_AGENT'] = API_USER_AGENT
        return self.app(environ, start_response)

class APIClient(FlaskClient):
    """Ensures that API endpoints are being invoked.
    """
    def get(self, url: str, *args, **kwargs) -> str:
        """Add API endpoint to URLs.
        """
        assert url[0] == '/'
        return super().get('/api' + url, *args, **kwargs)

    def post(self, url: str, *args, **kwargs) -> str:
        """Add API endpoint to URLs.
        """
        assert url[0] == '/'
        return super().post('/api' + url, *args, **kwargs)

####################
# mobile API stuff #
####################

MOBILE_API_USER_AGENT = "Mobile API test client"

class MobileAPIAppProxy:
    """From https://stackoverflow.com/q/15278285.
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['HTTP_USER_AGENT'] = MOBILE_API_USER_AGENT
        return self.app(environ, start_response)

class MobileAPIClient(FlaskClient):
    """Ensures that API endpoints are being invoked.
    """
    user: str = None

    def login(self, user: str, pw: str = '') -> bool:
        """Return `True` if successfully loggged in.
        """
        data = {'username': user, 'password': pw}
        resp = self.post("/login", data=data)
        assert resp.status_code == 200
        self.user = user
        api_resp = json.loads(resp.text)
        return api_resp['succ']

    def logout(self) -> dict:
        """Return `True` if successfully loggged out.
        """
        data = {}
        resp = self.post("/logout", data=data)
        assert resp.status_code == 200
        self.user = None
        api_resp = json.loads(resp.text)
        return api_resp['succ']

    def get(self, url: str, *args, **kwargs) -> str:
        """Add API endpoint to URLs.
        """
        assert url[0] == '/'
        return super().get('/mobile_api' + url, *args, **kwargs)

    def post(self, url: str, *args, **kwargs) -> str:
        """Add API endpoint to URLs.
        """
        assert url[0] == '/'
        return super().post('/mobile_api' + url, *args, **kwargs)
