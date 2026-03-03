# -*- coding: utf-8 -*-

"""Test admin API.  Note that this module was originally just a copy of test_admin (for
expediency), but we don't have to work too hard to keep them in sync.  It is fine if the
two diverge, for better coverage of areas more pertinent to the interface and/or clients.
"""

from collections.abc import Generator
from os import environ
import re
import json

import pytest
from flask import Flask
from flask.testing import FlaskClient

from conftest import TestConfig, APIAppProxy, APIClient, TEST_DB, ROSTER_FILE
from database import db_reset
from schema import TournStage, TournInfo, clear_schema_cache
from server import create_app

#################
# utility stuff #
#################

ADMIN_PW = environ.get('EUCHMGR_ADMIN_PW')
assert ADMIN_PW, "EUCHMGR_ADMIN_PW must be set in the env"

############
# fixtures #
############

@pytest.fixture(scope="module")
def api_app() -> Generator[Flask]:
    """Module-level app instantiation (caches database reference).
    """
    app = create_app(TestConfig)
    app.wsgi_app = APIAppProxy(app.wsgi_app)
    app.testing = True
    yield app
    # we do this because the run_auto sequence creates its own db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture(scope="module")
def api_client(api_app) -> Generator[FlaskClient]:
    """Module-level client instance.
    """
    app = api_app
    app.test_client_class = APIClient
    yield app.test_client()

#####################
# run_auto sequence #
#####################

def test_login(api_client):
    """
    """
    client = api_client
    data = {
        'username': "admin",
        'password': ADMIN_PW
    }
    resp = client.post("/login", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_create_tourn(api_client):
    """
    """
    client = api_client
    data = {
        'action'     : "create_tourn",
        'tourn_id'   : "",
        'tourn_name' : TEST_DB,
        'roster_file': open(ROSTER_FILE, "rb"),
        'overwrite'  : "yes"
    }
    resp = client.post("/tourn/create_tourn", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.PLAYER_ROSTER
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_get_tourn_data(api_client):
    """Validate that tourn_info data is populated.
    """
    client = api_client
    resp = client.get("/tourn/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    tourn_info = api_resp['data']
    assert isinstance(tourn_info, dict)
    assert tourn_info['id'] == tourn.id
    assert tourn_info['name'] == tourn.name

def test_players_data(api_client):
    """Validate that player data is populated, and sanity check for updates.

    NOTE: we are packing a lot into this test function, since there is no clean way to
    share the players data and manage dependencies between the subtest components (same
    with other data tests below).
    """
    client = api_client
    resp = client.get("/players/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == tourn.players
    players = api_resp['data']

    # validate that setting `player_num` works, and an empty `nick_name` is replaced by
    # `last_name` (and that `first_name` is then used in `display_name`)
    player = players[0]
    data = {
        'id'        : player['id'],
        'player_num': 10,
        'nick_name' : ''
    }
    resp = client.post("/players/", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    pl_data = api_resp['data']
    assert pl_data['id'] == data['id']
    assert pl_data['player_num'] == data['player_num']
    assert pl_data['nick_name'] == pl_data['last_name']
    assert pl_data['display_name'].find(f"({player['first_name']})") > -1

    # validate that `player_num` can be changed, and a non-empty `nick_name` is now used
    # in `display_name`
    player = players[0]
    data = {
        'id'        : player['id'],
        'player_num': 15,
        'nick_name' : "Zeke"
    }
    resp = client.post("/players/", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    pl_data = api_resp['data']
    assert pl_data['id'] == data['id']
    assert pl_data['player_num'] == data['player_num']
    assert pl_data['nick_name'] == data['nick_name']
    assert pl_data['display_name'].find(f"({data['nick_name']})") > -1

    # validate that same `player_num` cannot be reused
    player = players[1]
    data = {
        'id'        : player['id'],
        'player_num': 15,
        'nick_name' : ''
    }
    resp = client.post("/players/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'] == "Player Num already in use"

def test_gen_player_nums(api_client):
    """
    """
    client = api_client
    data = {
        'action': "gen_player_nums"
    }
    resp = client.post("/players/gen_player_nums", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.PLAYER_NUMS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_gen_seed_bracket(api_client):
    """
    """
    client = api_client
    data = {
        'action': "gen_seed_bracket"
    }
    resp = client.post("/players/gen_seed_bracket", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.SEED_BRACKET
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_seeding_data(api_client):
    """Validate that seeding round data is populated, and sanity check for updates.  See
    NOTE in `test_players_data` above.
    """
    client = api_client
    resp = client.get("/seeding/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    ngames = tourn.players // 4 * tourn.seed_rounds
    bye_recs = tourn.seed_rounds if (tourn.players % 4) else 0
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == ngames + bye_recs
    games = list(filter(lambda x: x['table_num'], api_resp['data']))
    byes = list(filter(lambda x: not x['table_num'], api_resp['data']))
    assert len(games) >= 1
    g1 = games[0]

    data = {
        'id'       : g1['id'],
        'team1_pts': 10,
        'team2_pts': 10
    }
    resp = client.post("/seeding/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'] == "Only one team can score game-winning points (10)"

    data = {
        'id'       : g1['id'],
        'team1_pts': 20,
        'team2_pts': 5
    }
    resp = client.post("/seeding/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'] == "Invalid score specified (must be between 0 and 10 points)"

    data = {
        'id'       : g1['id'],
        'team1_pts': "ten",
        'team2_pts': 5
    }
    resp = client.post("/seeding/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'] == "Invalid type specified"

    data = {
        'id'       : g1['id'],
        'team1_pts': 10,
        'team2_pts': 5
    }
    resp = client.post("/seeding/", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert not api_resp['err']

    data = {
        'id'       : g1['id'],
        'team1_pts': 5,
        'team2_pts': 10
    }
    resp = client.post("/seeding/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'] == "Completed game score cannot be overwritten"

def test_fake_seed_results(api_client):
    """
    """
    client = api_client
    data = {
        'action': "fake_seed_results"
    }
    resp = client.post("/seeding/fake_seed_results", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.SEED_RESULTS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_tabulate_seed_results(api_client):
    """
    """
    client = api_client
    data = {
        'action': "tabulate_seed_results"
    }
    resp = client.post("/seeding/tabulate_seed_results", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.SEED_RANKS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_partners_data(api_client):
    """Validate that partners data is populated, and (non-exhastive) sanity check for
    picks (additional test cases below, outside of this sequence due to need for data
    control).  See NOTE in `test_players_data` above.
    """
    client = api_client
    resp = client.get("/partners/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == tourn.players
    players = api_resp['data']

    avail = list(filter(lambda x: x['available'], players))
    taken = list(filter(lambda x: not x['available'], players))
    assert len(avail) >= 4
    assert len(taken) >= 2
    p1, p2, p3, p4 = avail[:4]
    # note that schema-wise these two are different (p5 is the picker, p6 is the pickee),
    # so we put both of them through the paces
    p5, p6 = taken[:2]

    # test cases:
    # - pick out of order (p3 picks p2)
    # - picker already taken (p5 picks p2)
    # - picker already taken (p6 picks p2)
    # - pick already taken (p1 picks p5)
    # - pick already taken (p1 picks p6)
    # - pick by rank (p1 picks p2)
    # - pick by name prefix already taken (p3 picks p1 by name)
    # - pick by name prefix already taken (p3 picks p2 by name)
    # - pick by name prefix (p3 picks p4 by name)

    OUT_OF_TURN  = r'Current pick belongs to .+ \([0-9]+\)'
    PICKER_TAKEN = r'Specified picker \(.*\) already on a team'
    PICK_TAKEN   = r'Specified pick \(.*\) already on a team'

    # pick out of order (p3 picks p2)
    data = {
        'id'        : p3['id'],
        'picks_info': p2['player_rank']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert re.match(OUT_OF_TURN, api_resp['err'])

    # picker already taken (p5 picks p2)
    data = {
        'id'        : p5['id'],
        'picks_info': p2['player_rank']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert re.match(PICKER_TAKEN, api_resp['err'])

    # picker already taken (p6 picks p2)
    data = {
        'id'        : p6['id'],
        'picks_info': p2['player_rank']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert re.match(PICKER_TAKEN, api_resp['err'])

    # pick already taken (p1 picks p5)
    data = {
        'id'        : p1['id'],
        'picks_info': p5['player_rank']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert re.match(PICK_TAKEN, api_resp['err'])

    # pick already taken (p1 picks p6)
    data = {
        'id'        : p1['id'],
        'picks_info': p6['player_rank']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert re.match(PICK_TAKEN, api_resp['err'])

    # pick by rank (p1 picks p2)
    data = {
        'id'        : p1['id'],
        'picks_info': p2['player_rank']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert not api_resp['err']

    # pick by name prefix already taken (p3 picks p1 by name)
    data = {
        'id'        : p3['id'],
        'picks_info': p1['nick_name']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert re.match(PICK_TAKEN, api_resp['err'])

    # pick by name prefix already taken (p3 picks p2 by name)
    data = {
        'id'        : p3['id'],
        'picks_info': p2['nick_name']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 400
    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert re.match(PICK_TAKEN, api_resp['err'])

    # pick by name prefix (p3 picks p4 by name)
    data = {
        'id'        : p3['id'],
        'picks_info': p4['nick_name']
    }
    resp = client.post("/partners/", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert not api_resp['err']

def test_fake_partner_picks(api_client):
    """
    """
    client = api_client
    data = {
        'action': "fake_partner_picks"
    }
    resp = client.post("/partners/fake_partner_picks", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.PARTNER_PICK
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_comp_team_seeds(api_client):
    """
    """
    client = api_client
    data = {
        'action': "comp_team_seeds"
    }
    resp = client.post("/partners/comp_team_seeds", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.TEAM_SEEDS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_teams_data(api_client):
    """Validate that teams data is populated.
    """
    client = api_client
    resp = client.get("/teams/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == tourn.teams

def test_gen_tourn_brackets(api_client):
    """
    """
    client = api_client
    data = {
        'action': "gen_tourn_brackets"
    }
    resp = client.post("/teams/gen_tourn_brackets", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.TOURN_BRACKET
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_round_robin_data(api_client):
    """Validate that round robin game data is populated.
    """
    client = api_client
    resp = client.get("/round_robin/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    ngames = tourn.teams // 2 * tourn.tourn_rounds
    bye_recs = tourn.tourn_rounds if (tourn.teams % 2) else 0
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == ngames + bye_recs

def test_fake_tourn_results(api_client):
    """
    """
    client = api_client
    data = {
        'action': "fake_tourn_results"
    }
    resp = client.post("/round_robin/fake_tourn_results", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.TOURN_RESULTS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_tabulate_tourn_results(api_client):
    """
    """
    client = api_client
    data = {
        'action': "tabulate_tourn_results"
    }
    resp = client.post("/round_robin/tabulate_tourn_results", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.TOURN_RANKS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_final_four_data(api_client):
    """Validate that final four teams data is populated.
    """
    client = api_client
    resp = client.get("/final_four/")
    assert resp.status_code == 200

    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == 4

def test_gen_semis_bracket(api_client):
    """
    """
    client = api_client
    data = {
        'action': "gen_semis_bracket"
    }
    resp = client.post("/final_four/gen_semis_bracket", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.SEMIS_BRACKET
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

####################
# tourn management #
####################

def test_pause_tourn(api_client):
    """
    """
    client = api_client
    tourn = TournInfo.get()
    data = {
        'action'    : "pause_tourn",
        'tourn_name': tourn.name
    }
    resp = client.post("/tourn/pause_tourn", data=data)
    assert resp.status_code == 200

    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert api_resp['info'] == f"Tournament \"{tourn.name}\" has been paused"

def test_create_tourn_exists(api_client):
    """
    """
    client = api_client
    data = {
        'action'     : "create_tourn",
        'tourn_id'   : "",
        'tourn_name' : TEST_DB,
        'roster_file': open(ROSTER_FILE, "rb"),
        'overwrite'  : ""
    }
    resp = client.post("/tourn/create_tourn", data=data)
    assert resp.status_code != 200

    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'].find(f"Tournament \"{TEST_DB}\" already exists") == 0

def test_resume_tourn(api_client):
    """
    """
    client = api_client
    data = {
        'action': "select_tourn",
        'tourn' : TEST_DB
    }
    resp = client.post("/tourn/select_tourn", data=data)
    assert resp.status_code == 200

    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert api_resp['info'] == f"Resuming operation of tournament \"{TEST_DB}\""

##################
# security tests #
##################

def test_logout(api_client):
    """
    """
    client = api_client
    data = {}
    resp = client.post("/logout", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert api_resp['info'] == 'User \\"admin\\" logged out'

def test_get_tourn_data_noauth(api_client):
    """Try getting tourn management view without authorization.
    """
    client = api_client
    resp = client.get("/tourn/")
    assert resp.status_code == 401

    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'] == "Unauthorized"

######################
# partner pick cases #
######################

"""
individual test cases:
- no available players
- invalid rank specified
- no match for name prefix
- multiple nane match, ambiguous
- multiple name match, none available
- pick by name prefix (partial)
- multiple name match, one one available
"""
