# -*- coding: utf-8 -*-

"""Test admin API.  Note that this module was originally just a copy of test_admin (for
expediency), but we don't have to work too hard to keep them in sync.  It is fine if the
two diverge, for better coverage of areas more pertinent to the interface and/or clients.
"""

from os import environ
import re
import json

import pytest

from conftest import TEST_DB
from test_basic import ROSTER_FILE
from schema import TournStage, TournInfo

#################
# utility stuff #
#################

ADMIN_PW = environ.get('EUCHMGR_ADMIN_PW')
assert ADMIN_PW, "EUCHMGR_ADMIN_PW must be set in the env"

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
    resp = client.post("/api/login", data=data)
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
    resp = client.post("/api/tourn/create_tourn", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.PLAYER_ROSTER
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_get_tourn_data(api_client):
    """Validate that tourn_info data is populated.
    """
    client = api_client
    resp = client.get("/api/tourn/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    tourn_info = api_resp['data']
    assert isinstance(tourn_info, dict)
    assert tourn_info['id'] == tourn.id
    assert tourn_info['name'] == tourn.name

def test_get_players_data(api_client):
    """Validate that player data is populated.
    """
    client = api_client
    resp = client.get("/api/players/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == tourn.players

def test_gen_player_nums(api_client):
    """
    """
    client = api_client
    data = {
        'action': "gen_player_nums"
    }
    resp = client.post("/api/players/gen_player_nums", data=data)
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
    resp = client.post("/api/players/gen_seed_bracket", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.SEED_BRACKET
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_get_seeding_data(api_client):
    """Validate that seeding round data is populated.
    """
    client = api_client
    resp = client.get("/api/seeding/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    ngames = tourn.players // 4 * tourn.seed_rounds
    bye_recs = tourn.seed_rounds if (tourn.players % 4) else 0
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == ngames + bye_recs

def test_fake_seed_results(api_client):
    """
    """
    client = api_client
    data = {
        'action': "fake_seed_results"
    }
    resp = client.post("/api/seeding/fake_seed_results", data=data)
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
    resp = client.post("/api/seeding/tabulate_seed_results", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.SEED_RANKS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_get_partners_data(api_client):
    """Validate that partners data is populated.
    """
    client = api_client
    resp = client.get("/api/partners/")
    assert resp.status_code == 200

    tourn = TournInfo.get()
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert isinstance(api_resp['data'], list)
    assert len(api_resp['data']) == tourn.players

def test_fake_partner_picks(api_client):
    """
    """
    client = api_client
    data = {
        'action': "fake_partner_picks"
    }
    resp = client.post("/api/partners/fake_partner_picks", data=data)
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
    resp = client.post("/api/partners/comp_team_seeds", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.TEAM_SEEDS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_get_teams_data(api_client):
    """Validate that teams data is populated.
    """
    client = api_client
    resp = client.get("/api/teams/")
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
    resp = client.post("/api/teams/gen_tourn_brackets", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.TOURN_BRACKET
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_get_round_robin_data(api_client):
    """Validate that round robin game data is populated.
    """
    client = api_client
    resp = client.get("/api/round_robin/")
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
    resp = client.post("/api/round_robin/fake_tourn_results", data=data)
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
    resp = client.post("/api/round_robin/tabulate_tourn_results", data=data)
    assert resp.status_code == 200

    tourn = TournInfo.get()
    assert tourn.stage_compl == TournStage.TOURN_RANKS
    api_resp = json.loads(resp.text)
    assert api_resp['succ']

def test_get_final_four_data(api_client):
    """Validate that final four teams data is populated.
    """
    client = api_client
    resp = client.get("/api/final_four/")
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
    resp = client.post("/api/final_four/gen_semis_bracket", data=data)
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
    resp = client.post("/api/tourn/pause_tourn", data=data)
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
    resp = client.post("/api/tourn/create_tourn", data=data)
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
    resp = client.post("/api/tourn/select_tourn", data=data)
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
    resp = client.post("/api/logout", data=data)
    assert resp.status_code == 200
    api_resp = json.loads(resp.text)
    assert api_resp['succ']
    assert api_resp['info'] == 'User \\"admin\\" logged out'

def test_get_tourn_data_noauth(api_client):
    """Try getting tourn management view without authorization.
    """
    client = api_client
    resp = client.get("/api/tourn/")
    assert resp.status_code == 401

    api_resp = json.loads(resp.text)
    assert not api_resp['succ']
    assert api_resp['err'] == "Unauthorized"
