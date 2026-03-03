# -*- coding: utf-8 -*-

"""Base end-to-end test sequence (the "auto_run" sequence).  Also builds database fixtures
for stage-level testing.  Note that this is a "happy path" scenario that doesn't exercise
any error/failure modes and/or handlers.
"""

from collections.abc import Generator

import pytest
from peewee import SqliteDatabase

from conftest import TEST_DB, ROSTER_FILE, RAND_SEEDS, save_stage_db
from database import db_init, db_reset
from schema import Bracket, TournStage, TournInfo, clear_schema_cache
from euchmgr import (tourn_create, upload_roster, generate_player_nums, build_seed_bracket,
                     fake_seed_games, validate_seed_round, compute_player_ranks,
                     prepick_champ_partners, fake_pick_partners, build_tourn_teams,
                     compute_team_seeds, build_tourn_bracket, fake_tourn_games,
                     validate_tourn, compute_team_ranks, build_playoff_bracket)

############
# fixtures #
############

@pytest.fixture(scope="module")
def test_db() -> Generator[SqliteDatabase]:
    """Module-level database instance.
    """
    db = db_init(TEST_DB, force=True)
    yield db
    db_reset(force=True)
    clear_schema_cache()

#####################
# run_auto sequence #
#####################

def test_tourn_create(test_db) -> None:
    """
    """
    tourn_info = tourn_create(force=True)
    assert tourn_info.name == TEST_DB
    assert tourn_info.stage_compl == TournStage.TOURN_CREATE
    save_stage_db(TournStage.TOURN_CREATE)

def test_upload_roster(test_db) -> None:
    """
    """
    upload_roster(ROSTER_FILE)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PLAYER_ROSTER
    save_stage_db(TournStage.PLAYER_ROSTER)

def test_generate_player_nums(test_db) -> None:
    """
    """
    generate_player_nums(rand_seed=RAND_SEEDS[0])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PLAYER_NUMS
    save_stage_db(TournStage.PLAYER_NUMS)

def test_build_seed_bracket(test_db) -> None:
    """
    """
    build_seed_bracket()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_BRACKET
    save_stage_db(TournStage.SEED_BRACKET)

def test_fake_seed_games(test_db) -> None:
    """
    """
    fake_seed_games(rand_seed=RAND_SEEDS[1])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RESULTS
    save_stage_db(TournStage.SEED_RESULTS)

def test_validate_seed_round(test_db) -> None:
    """
    """
    validate_seed_round(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_TABULATE
    save_stage_db(TournStage.SEED_TABULATE)

def test_compute_player_ranks(test_db) -> None:
    """
    """
    compute_player_ranks(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RANKS
    save_stage_db(TournStage.SEED_RANKS)

def test_prepick_champ_partners(test_db) -> None:
    """
    """
    prepick_champ_partners()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RANKS
    # REVISIT: are we not creating a snapshot here???
    # TODO: assert action taken!

def test_fake_pick_partners(test_db) -> None:
    """
    """
    fake_pick_partners(rand_seed=RAND_SEEDS[2])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PARTNER_PICK
    save_stage_db(TournStage.PARTNER_PICK)

def test_build_tourn_teams(test_db) -> None:
    """
    """
    build_tourn_teams()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_TEAMS
    save_stage_db(TournStage.TOURN_TEAMS)

def test_compute_team_seeds(test_db) -> None:
    """
    """
    compute_team_seeds()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TEAM_SEEDS
    save_stage_db(TournStage.TEAM_SEEDS)

def test_build_tourn_bracket(test_db) -> None:
    """
    """
    build_tourn_bracket()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_BRACKET
    save_stage_db(TournStage.TOURN_BRACKET)

def test_fake_tourn_games(test_db) -> None:
    """
    """
    fake_tourn_games(rand_seed=RAND_SEEDS[3])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_RESULTS
    save_stage_db(TournStage.TOURN_RESULTS)

def test_validate_tourn(test_db) -> None:
    """
    """
    validate_tourn(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_TABULATE
    save_stage_db(TournStage.TOURN_TABULATE)

def test_compute_team_ranks(test_db) -> None:
    """
    """
    compute_team_ranks(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_RANKS
    save_stage_db(TournStage.TOURN_RANKS)

def test_build_playoff_bracket(test_db) -> None:
    """
    """
    build_playoff_bracket(Bracket.SEMIS)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEMIS_BRACKET
    save_stage_db(TournStage.SEMIS_BRACKET)
