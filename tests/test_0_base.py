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
    """Note that the yield value for this function can easily be ignored (e.g. we can use
    this with the `usefixtures` marker).
    """
    db = db_init(TEST_DB, force=True)
    yield db
    db_reset(force=True)
    clear_schema_cache()

#####################
# run_auto sequence #
#####################

def test_end_to_end(test_db) -> None:
    """
    """
    tourn_info = tourn_create(force=True)
    assert tourn_info.name == TEST_DB
    assert tourn_info.stage_compl == TournStage.TOURN_CREATE
    save_stage_db(TournStage.TOURN_CREATE)

    upload_roster(ROSTER_FILE)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PLAYER_ROSTER
    save_stage_db(TournStage.PLAYER_ROSTER)

    generate_player_nums(rand_seed=RAND_SEEDS[0])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PLAYER_NUMS
    save_stage_db(TournStage.PLAYER_NUMS)

    build_seed_bracket()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_BRACKET
    save_stage_db(TournStage.SEED_BRACKET)

    fake_seed_games(rand_seed=RAND_SEEDS[1])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RESULTS
    save_stage_db(TournStage.SEED_RESULTS)

    validate_seed_round(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_TABULATE
    save_stage_db(TournStage.SEED_TABULATE)

    compute_player_ranks(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RANKS
    save_stage_db(TournStage.SEED_RANKS)

    prepick_champ_partners()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEED_RANKS
    # REVISIT: are we not creating a snapshot here???
    # TODO: assert action taken!

    fake_pick_partners(rand_seed=RAND_SEEDS[2])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.PARTNER_PICK
    save_stage_db(TournStage.PARTNER_PICK)

    build_tourn_teams()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_TEAMS
    save_stage_db(TournStage.TOURN_TEAMS)

    compute_team_seeds()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TEAM_SEEDS
    save_stage_db(TournStage.TEAM_SEEDS)

    build_tourn_bracket()
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_BRACKET
    save_stage_db(TournStage.TOURN_BRACKET)

    fake_tourn_games(rand_seed=RAND_SEEDS[3])
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_RESULTS
    save_stage_db(TournStage.TOURN_RESULTS)

    validate_tourn(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_TABULATE
    save_stage_db(TournStage.TOURN_TABULATE)

    compute_team_ranks(finalize=True)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.TOURN_RANKS
    save_stage_db(TournStage.TOURN_RANKS)

    build_playoff_bracket(Bracket.SEMIS)
    tourn_info = TournInfo.get()
    assert tourn_info.stage_compl == TournStage.SEMIS_BRACKET
    save_stage_db(TournStage.SEMIS_BRACKET)
