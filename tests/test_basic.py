# -*- coding: utf-8 -*-

"""Basic end-to-end test sequence.  Also builds database fixtures for stage-level testing.

"""
from collections.abc import Generator
import pytest
from peewee import SqliteDatabase

from core import TEST_DIR, DataFile
from database import db_init, db_name
from schema import TournStage, TournInfo
from euchmgr import (tourn_create, upload_roster, generate_player_nums, build_seed_bracket,
                     fake_seed_games, validate_seed_round, compute_player_ranks,
                     prepick_champ_partners, fake_pick_partners, build_tourn_teams,
                     compute_team_seeds, build_tourn_bracket, fake_tourn_games,
                     validate_tourn, compute_team_ranks)

TOURN_NAME = "test"
ROSTER_FILE = DataFile("test_roster.csv", TEST_DIR)
RAND_SEEDS = list(x * 10 for x in range(10))

@pytest.fixture
def tourn_db() -> Generator[SqliteDatabase]:
    db = db_init(TOURN_NAME)
    yield db
    db.close()

def test_end_to_end(tourn_db: SqliteDatabase) -> None:
    """Same as `run_auto.sh` script; also builds stage-level database snapshots.
    """
    tourn_info = tourn_create(force=True)
    assert tourn_info.name == TOURN_NAME
    assert tourn_info.stage_compl == TournStage.TOURN_CREATE

    upload_roster(ROSTER_FILE)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PLAYER_ROSTER

    generate_player_nums(rand_seed=RAND_SEEDS[0])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PLAYER_NUMS

    build_seed_bracket()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_BRACKET

    fake_seed_games(rand_seed=RAND_SEEDS[1])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RESULTS

    validate_seed_round(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_TABULATE

    compute_player_ranks(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RANKS

    prepick_champ_partners()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RANKS
    # TODO: assert action taken!

    fake_pick_partners(rand_seed=RAND_SEEDS[2])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PARTNER_PICK

    build_tourn_teams()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_TEAMS

    compute_team_seeds()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TEAM_SEEDS

    build_tourn_bracket()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_BRACKET

    fake_tourn_games(rand_seed=RAND_SEEDS[3])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_RESULTS

    validate_tourn(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_TABULATE

    compute_team_ranks(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TEAM_RANKS
