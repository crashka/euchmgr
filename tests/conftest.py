# -*- coding: utf-8 -*-

"""Common constants, fixtures, etc.
"""
from collections.abc import Generator

import pytest
from peewee import SqliteDatabase

from core import TEST_DIR
from database import db_init, db_close, db_name, build_filename
from schema import TournStage

#############
# Constants #
#############

TEST_DB = "test"

#################
# Utility Funcs #
#################

def stage_db_path(stage_num: int) -> str:
    """Build full pathname for stage-level database snapshot.
    """
    name = f"{db_name()}-stage-{stage_num}"
    return build_filename(name, TEST_DIR)

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
    shutil.copy2(stage_db_path(stage), db.database)
    return db

############
# Fixtures #
############

@pytest.fixture
def stage_1_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(1))
    return db

@pytest.fixture
def stage_2_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(2))
    return db

@pytest.fixture
def stage_3_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(3))
    return db

@pytest.fixture
def stage_4_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(4))
    return db

@pytest.fixture
def stage_5_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(5))
    return db

@pytest.fixture
def stage_6_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(6))
    return db

@pytest.fixture
def stage_7_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(7))
    return db

@pytest.fixture
def stage_8_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(8))
    return db

@pytest.fixture
def stage_9_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(9))
    return db

@pytest.fixture
def stage_10_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(10))
    return db

@pytest.fixture
def stage_11_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(11))
    return db

@pytest.fixture
def stage_12_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(12))
    return db

@pytest.fixture
def stage_13_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(13))
    return db

@pytest.fixture
def stage_14_db() -> SqliteDatabase:
    db = restore_stage_db(TournStage(14))
    return db

@pytest.fixture
def test_db() -> Generator[SqliteDatabase]:
    db = db_init(TEST_DB)
    yield db
    db.close()
