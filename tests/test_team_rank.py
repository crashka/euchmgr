# -*- coding: utf-8 -*-

"""Test team ranking process, including tie-breaking logic.
"""
from collections.abc import Generator

import pytest

from database import db_close
from schema import Team, TournGame
from euchmgr import cyclic_win_groups, elevate_winners

# (nteams, ref_cycle_grps), where groups are represented by team seeds
CycleFixture = tuple[int, list[set[int]]]

def get_team_map() -> dict[int: Team]:
    """Stand-in for function removed from schema.
    """
    return {tm.id: tm for tm in Team.iter_teams()}

def add_games(gm_defs: list[tuple]) -> None:
    """Add TournGame entries (and associated TeamGame records) based on specified game
    definitions.  `gm_defs` tuples have the following fields: (team1_id, team2_id,
    team1_pts, team2_pts)
    """
    tm_map = get_team_map()

    for i, gm_def in enumerate(gm_defs):
        team1 = tm_map[gm_def[0]]
        team2 = tm_map[gm_def[1]]
        pts1  = gm_def[2]
        pts2  = gm_def[3]
        info = {'div_num'       : 0,
                'round_num'     : i,
                'table_num'     : 0,
                'label'         : f"test-{i}",
                'team1'         : team1,
                'team2'         : team2,
                'team1_name'    : team1.team_name,
                'team2_name'    : team2.team_name,
                'bye_team'      : None,
                'team1_div_seed': team1.div_seed,
                'team2_div_seed': team2.div_seed,
                'team1_pts'     : pts1,
                'team2_pts'     : pts2}
        game = TournGame.create(**info)
        game.insert_team_games()

@pytest.fixture
def non_cycle(stage_10_db) -> Generator[CycleFixture]:
    """No cyclical win groups"""
    gm_defs = [(1, 2, 10, 5),
               (1, 3, 10, 5),
               (2, 3, 10, 5),
               (4, 3, 10, 5)]
    add_games(gm_defs)
    nteams = max(map(lambda x: max(x[0], x[1]), gm_defs))
    yield nteams, []
    db_close()

@pytest.fixture
def simple_cycle(stage_10_db) -> Generator[CycleFixture]:
    """Simplest example of a cycle"""
    gm_defs = [(1, 2, 10, 5),
               (2, 3, 10, 5),
               (3, 1, 10, 5)]
    add_games(gm_defs)
    nteams = max(map(lambda x: max(x[0], x[1]), gm_defs))
    yield nteams, [{1, 2, 3}]
    db_close()

@pytest.fixture
def simple_cycle2(stage_10_db) -> Generator[CycleFixture]:
    """Cycle where starting node does not participate"""
    gm_defs = [(1, 2, 10, 5),
               (1, 3, 10, 5),
               (2, 3, 10, 5),
               (4, 2, 10, 5),
               (3, 4, 10, 5)]
    add_games(gm_defs)
    nteams = max(map(lambda x: max(x[0], x[1]), gm_defs))
    yield nteams, [{2, 3, 4}]
    db_close()

@pytest.fixture
def double_cycle(stage_10_db) -> Generator[CycleFixture]:
    """Team participating in two cycle"""
    gm_defs = [(1, 2, 10, 5),
               (2, 3, 10, 5),
               (3, 1, 10, 5),
               (1, 4, 10, 5),
               (4, 5, 10, 5),
               (5, 1, 10, 5)]
    add_games(gm_defs)
    nteams = max(map(lambda x: max(x[0], x[1]), gm_defs))
    yield nteams, [{1, 2, 3}, {1, 4, 5}]
    db_close()

@pytest.fixture
def double_cycle2(stage_10_db) -> Generator[CycleFixture]:
    """Cycle within a cycle"""
    gm_defs = [(1, 2, 10, 5),
               (2, 3, 10, 5),
               (3, 4, 10, 5),
               (4, 1, 10, 5),
               (2, 4, 10, 5)]
    add_games(gm_defs)
    nteams = max(map(lambda x: max(x[0], x[1]), gm_defs))
    yield nteams, [{1, 2, 3, 4}, {1, 2, 4}]
    db_close()

@pytest.fixture
def simple_elevate(stage_10_db) -> Generator[CycleFixture]:
    """Simple elevation example (no cycles)"""
    gm_defs = [(1, 2, 10, 0),
               (1, 3, 10, 0),
               (4, 1, 10, 5),
               (4, 2, 10, 5)]
    add_games(gm_defs)
    nteams = max(map(lambda x: max(x[0], x[1]), gm_defs))
    yield nteams, [(4, 1)]
    db_close()

@pytest.fixture
def identical_tbs(stage_14_db) -> tuple[tuple[int, int], list[float], int]:
    """Identical tie-breaker criteria"""
    test_crit = [1.1, 2.2, 3.3, 4.4]
    upd = (Team
           .update(div_tb_crit=test_crit)
           .where(Team.div_num == 1,
                  Team.div_pos == 2))
    res = upd.execute()
    yield (1, 2), [test_crit], [res]
    db_close()

def validate_cycle_grps(result: CycleFixture) -> None:
    nteams, ref_cycle_grps = result
    tm_map = get_team_map()
    teams = [tm_map[i] for i in range(1, nteams + 1)]
    cycle_grps, _ = cyclic_win_groups(teams)
    assert len(cycle_grps) == len(ref_cycle_grps)
    for grp in cycle_grps:
        assert set(tm.id for tm in grp) in ref_cycle_grps

def test_non_cycle(non_cycle) -> None:
    validate_cycle_grps(non_cycle)

def test_simple_cycle(simple_cycle) -> None:
    validate_cycle_grps(simple_cycle)

def test_simple_cycle2(simple_cycle2) -> None:
    validate_cycle_grps(simple_cycle2)

def test_double_cycle(double_cycle) -> None:
    validate_cycle_grps(double_cycle)

def test_double_cycle2(double_cycle2) -> None:
    validate_cycle_grps(double_cycle2)

def test_simple_elevate(simple_elevate) -> None:
    nteams, ref_elevs = simple_elevate
    tm_map = get_team_map()
    teams = [tm_map[i] for i in range(1, nteams + 1)]
    _, elevs, _, _ = elevate_winners(teams)
    assert len(elevs) == len(ref_elevs)
    for i, elev in enumerate(elevs):
        assert tuple(tm.id for tm in elev) == ref_elevs[i]

def test_identical_tbs(identical_tbs) -> None:
    div_pos, ref_tb_crits, team_cts = identical_tbs
    tbs = Team.ident_div_tbs(div_pos[0], div_pos[1])
    assert len(tbs) == len(ref_tb_crits)
    for i, teams in enumerate(tbs):
        assert len(teams) == team_cts[i]
        assert teams[0].div_tb_crit == ref_tb_crits[i]
