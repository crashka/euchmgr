# -*- coding: utf-8 -*-

"""Test admin UI.
"""
import re
import json

import pytest
from flask import session
from bs4 import BeautifulSoup, Tag

from conftest import TEST_DB, get_user_client
from test_basic import ROSTER_FILE
from schema import TournStage, TournInfo
from admin import View, VIEW_DEFS, SEL_NEW

#####################
# utility functions #
#####################

def validate_stage(soup: BeautifulSoup, stage: TournStage) -> TournInfo:
    """Validate tournament stage in view info section.  Return `tourn` as a convenience.
    """
    tourn = TournInfo.get()
    assert tourn.stage_compl == stage

    sect = soup.select_one('section.tourn_info')
    assert sect
    assert sect.select_one('input[name="cur_stage"]')
    assert sect.select_one('input[name="cur_stage"]')['value'] == tourn.cur_stage
    assert sect.select_one('input[name="next_action"]')
    assert sect.select_one('input[name="next_action"]')['value'] == (tourn.next_action or '')

def validate_view(soup: BeautifulSoup, view: View) -> None:
    """Validate that we have the specified view.
    """
    view_info = VIEW_DEFS[view]
    nav_input = soup.select_one('.view_sel input[checked]')
    assert nav_input['value'] == view
    assert nav_input.parent.text == view_info.name
    view_title = soup.select_one('.view_body h2')
    # could use .string here, but doing this for consistency
    assert view_title.text == view_info.name

def validate_button(parent: Tag, btn_value: str, enabled: bool) -> None:
    """Validate state of button.
    """
    assert parent
    selector = f'button[value="{btn_value}"]'
    assert parent.select_one(selector)
    assert parent.select_one(selector).get('disabled') == (None if enabled else '')

#####################
# run_auto sequence #
#####################

def test_index(admin_client):
    """Starting with a cleared session, GET on '/' should return admin login page.
    """
    client = admin_client
    with client.session_transaction() as session:
        session.clear()
    resp = client.get('/', follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/login'

    soup = BeautifulSoup(resp.text, 'html.parser')
    form = soup.select_one('form[action="/login"]')
    assert form
    select = form.select_one('select[name="username"]')
    assert select
    options = select.select('option')
    assert len(options) == 1
    assert options[0].get('value') == 'admin'
    assert options[0].get('selected') is not None
    assert options[0].string == 'admin'

def test_login(admin_client):
    """Logging in as admin should return tournament selection view.
    """
    client = admin_client
    data = {
        'username': "admin",
        'password': "119baystate"
    }
    resp = client.post("/login", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 2
    assert resp.request.path == '/tourn'

    soup = BeautifulSoup(resp.text, 'html.parser')
    assert not soup.select('section.tourn')

    form = soup.select_one('form[action="/tourn/select_tourn"]')
    assert form
    select = form.select_one('select[name="tourn"]')
    assert select
    assert select.select('option[disabled][selected][hidden]')
    assert select.select_one(f'option[value="{SEL_NEW}"]')
    assert select.select_one(f'option[value="{SEL_NEW}"]').string == SEL_NEW

def test_create_new(admin_client):
    """Selecting "(create new)" should return create tournament view.
    """
    client = admin_client
    data = {
        'action': "select_tourn",
        'tourn' : SEL_NEW
    }
    resp = client.post("/tourn/select_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/tourn'

    soup = BeautifulSoup(resp.text, 'html.parser')
    assert soup.select('section.tourn')

    form = soup.select_one('form[action="/tourn/select_tourn"]')
    assert form
    select = form.select_one('select[name="tourn"]')
    assert select
    assert select.select(f'option[value="{SEL_NEW}"][selected]')

    form = soup.select_one('form[action="/tourn"]')
    assert form
    assert form.select('input[name="tourn_id"]')
    assert form.select('input[name="tourn_name"]')
    assert form.select('input[name="roster_file"]')
    assert form.select('input[name="overwrite"]')
    validate_button(form, "create_tourn", True)

def test_create_tourn_overwrite(admin_client):
    """Creating a new tournament should return the Players view.
    """
    client = admin_client
    data = {
        'action'     : "create_tourn",
        'tourn_id'   : "",
        'tourn_name' : TEST_DB,
        'roster_file': open(ROSTER_FILE, "rb"),
        'overwrite'  : "yes"
    }
    resp = client.post("/tourn/create_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/players'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.PLAYERS)
    validate_stage(soup, TournStage.PLAYER_ROSTER)

    form = soup.select_one('form.actions[action="players"]')
    validate_button(form, "gen_player_nums", True)
    validate_button(form, "gen_seed_bracket", False)

def test_get_players_data(admin_client):
    """Validate that player data is populated.
    """
    client = admin_client
    resp = client.get("/players/data", follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 0
    assert resp.request.path == '/players/data'

    tourn = TournInfo.get()
    ajax_resp = json.loads(resp.text)
    assert ajax_resp['succ']
    assert isinstance(ajax_resp['data'], list)
    assert len(ajax_resp['data']) == tourn.players

def test_gen_player_nums(admin_client):
    """Generating player nums should enable the `gen_seed_bracket` button.
    """
    client = admin_client
    data = {
        'action': "gen_player_nums"
    }
    resp = client.post("/players/gen_player_nums", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/players'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.PLAYERS)
    validate_stage(soup, TournStage.PLAYER_NUMS)

    form = soup.select_one('form.actions[action="players"]')
    validate_button(form, "gen_player_nums", False)
    validate_button(form, "gen_seed_bracket", True)

def test_gen_seed_bracket(admin_client):
    """Generating seed bracket should return the Seeding view.
    """
    client = admin_client
    data = {
        'action': "gen_seed_bracket"
    }
    resp = client.post("/players/gen_seed_bracket", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/seeding'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.SEEDING)
    validate_stage(soup, TournStage.SEED_BRACKET)

    form = soup.select_one('form.actions[action="seeding"]')
    validate_button(form, "fake_seed_results", True)
    validate_button(form, "tabulate_seed_results", False)

def test_get_seeding_data(admin_client):
    """Validate that seeding round data is populated.
    """
    client = admin_client
    resp = client.get("/seeding/data", follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 0
    assert resp.request.path == '/seeding/data'

    tourn = TournInfo.get()
    ngames = tourn.players // 4 * tourn.seed_rounds
    bye_recs = tourn.seed_rounds if (tourn.players % 4) else 0
    ajax_resp = json.loads(resp.text)
    assert ajax_resp['succ']
    assert isinstance(ajax_resp['data'], list)
    assert len(ajax_resp['data']) == ngames + bye_recs

def test_fake_seed_results(admin_client):
    """Generating fake seed results should enable the `tabulate_seed_results` button.
    """
    client = admin_client
    data = {
        'action': "fake_seed_results"
    }
    resp = client.post("/seeding/fake_seed_results", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/seeding'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.SEEDING)
    validate_stage(soup, TournStage.SEED_RESULTS)

    form = soup.select_one('form.actions[action="seeding"]')
    validate_button(form, "fake_seed_results", False)
    validate_button(form, "tabulate_seed_results", True)

def test_tabulate_seed_results(admin_client):
    """Tabulating seed results should return the Partners view.
    """
    client = admin_client
    data = {
        'action': "tabulate_seed_results"
    }
    resp = client.post("/seeding/tabulate_seed_results", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/partners'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.PARTNERS)
    validate_stage(soup, TournStage.SEED_RANKS)

    form = soup.select_one('form.actions[action="partners"]')
    validate_button(form, "fake_partner_picks", True)
    validate_button(form, "comp_team_seeds", False)

def test_fake_partner_picks(admin_client):
    """Generating fake partner picks should enable the `comp_team_seeds` button.
    """
    client = admin_client
    data = {
        'action': "fake_partner_picks"
    }
    resp = client.post("/partners/fake_partner_picks", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/partners'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.PARTNERS)
    validate_stage(soup, TournStage.PARTNER_PICK)

    form = soup.select_one('form.actions[action="partners"]')
    validate_button(form, "fake_partner_picks", False)
    validate_button(form, "comp_team_seeds", True)

def test_comp_team_seeds(admin_client):
    """Computing team seeds should return the Teams view.
    """
    client = admin_client
    data = {
        'action': "comp_team_seeds"
    }
    resp = client.post("/partners/comp_team_seeds", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/teams'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.TEAMS)
    validate_stage(soup, TournStage.TEAM_SEEDS)

    form = soup.select_one('form.actions[action="teams"]')
    validate_button(form, "gen_tourn_brackets", True)

def test_gen_tourn_brackets(admin_client):
    """Generating tourn brackets should return the Round Robin view.
    """
    client = admin_client
    data = {
        'action': "gen_tourn_brackets"
    }
    resp = client.post("/teams/gen_tourn_brackets", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/round_robin'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.ROUND_ROBIN)
    validate_stage(soup, TournStage.TOURN_BRACKET)

    form = soup.select_one('form.actions[action="round_robin"]')
    validate_button(form, "fake_tourn_results", True)
    validate_button(form, "tabulate_tourn_results", False)

def test_get_round_robin_data(admin_client):
    """Validate that round robin game data is populated.
    """
    client = admin_client
    resp = client.get("/round_robin/data", follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 0
    assert resp.request.path == '/round_robin/data'

    tourn = TournInfo.get()
    ngames = tourn.teams // 2 * tourn.tourn_rounds
    bye_recs = tourn.tourn_rounds if (tourn.teams % 2) else 0
    ajax_resp = json.loads(resp.text)
    assert ajax_resp['succ']
    assert isinstance(ajax_resp['data'], list)
    assert len(ajax_resp['data']) == ngames + bye_recs

def test_fake_tourn_results(admin_client):
    """Generating fake tourn results should enable the `tabulate_tourn_results` button.
    """
    client = admin_client
    data = {
        'action': "fake_tourn_results"
    }
    resp = client.post("/round_robin/fake_tourn_results", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/round_robin'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.ROUND_ROBIN)
    validate_stage(soup, TournStage.TOURN_RESULTS)

    form = soup.select_one('form.actions[action="round_robin"]')
    validate_button(form, "fake_tourn_results", False)
    validate_button(form, "tabulate_tourn_results", True)

def test_tabulate_tourn_results(admin_client):
    """Tabulating tourn results should return the Final Four view.
    """
    client = admin_client
    data = {
        'action': "tabulate_tourn_results"
    }
    resp = client.post("/round_robin/tabulate_tourn_results", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/final_four'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.FINAL_FOUR)
    validate_stage(soup, TournStage.TOURN_RANKS)

    form = soup.select_one('form.actions[action="final_four"]')
    validate_button(form, "gen_semis_bracket", True)
    validate_button(form, "gen_finals_bracket", False)

def test_gen_semis_bracket(admin_client):
    """Generating semis bracket should return the Playoffs view.
    """
    client = admin_client
    data = {
        'action': "gen_semis_bracket"
    }
    resp = client.post("/final_four/gen_semis_bracket", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/playoffs'

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.PLAYOFFS)
    validate_stage(soup, TournStage.SEMIS_BRACKET)

    form = soup.select_one('form.actions[action="playoffs"]')
    validate_button(form, "tabulate_semis_results", False)
    validate_button(form, "tabulate_finals_results", False)

#############################
# tourn management sequence #
#############################

def test_manage_tourn(admin_client):
    """Go to manage tourn view for active tournament.
    """
    client = admin_client
    resp = client.get("/tourn", follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 0
    assert resp.request.path == '/tourn'

    tourn = TournInfo.get()
    soup = BeautifulSoup(resp.text, 'html.parser')
    form = soup.select_one('form[action="/tourn/select_tourn"]')
    assert form
    select = form.select_one('select[name="tourn"]')
    assert select
    assert select.select(f'option[value="{tourn.name}"][selected]')

    form = soup.select_one('form[action="/tourn"]')
    assert form
    assert form.select_one('input[name="tourn_id"]')
    assert form.select_one('input[name="tourn_id"]')['value'] == str(tourn.id)
    assert form.select_one('input[name="tourn_name"]')
    assert form.select_one('input[name="tourn_name"]')['value'] == tourn.name
    assert not form.select('input[name="roster_file"]')
    assert not form.select('input[name="overwrite"]')
    validate_button(form, "update_tourn", True)
    validate_button(form, "pause_tourn", True)

def test_pause_tourn(admin_client):
    """Generating semis bracket should return the Playoffs view.
    """
    client = admin_client
    tourn = TournInfo.get()
    data = {
        'action'    : "pause_tourn",
        'tourn_name': tourn.name
    }
    resp = client.post("/tourn/pause_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 2
    assert resp.request.path == '/tourn'
    err_msg = f"showError(\'Tournament \"{tourn.name}\" has been paused"
    assert resp.text.find(err_msg) > -1

    soup = BeautifulSoup(resp.text, 'html.parser')
    assert not soup.select('section.tourn')

    form = soup.select_one('form[action="/tourn/select_tourn"]')
    assert form
    select = form.select_one('select[name="tourn"]')
    assert select
    assert select.select('option[disabled][selected][hidden]')
    assert select.select_one(f'option[value="{tourn.name}"]')
    assert select.select_one(f'option[value="{tourn.name}"]').string == tourn.name

def test_create_tourn_exists(admin_client):
    """Creating a new tournament should return the Players view.
    """
    client = admin_client
    data = {
        'action'     : "create_tourn",
        'tourn_id'   : "",
        'tourn_name' : TEST_DB,
        'roster_file': open(ROSTER_FILE, "rb"),
        'overwrite'  : ""
    }
    resp = client.post("/tourn/create_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 0
    assert resp.request.path == '/tourn/create_tourn'
    err_msg = f"showError(\'Tournament \"{TEST_DB}\" already exists"
    assert resp.text.find(err_msg) > -1

def test_resume_tourn(admin_client):
    """Resuming the tournament should bring us back to the Playoffs view.
    """
    client = admin_client
    data = {
        'action': "select_tourn",
        'tourn' : TEST_DB
    }
    resp = client.post("/tourn/select_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 2
    assert resp.request.path == '/playoffs'
    err_msg = f"showError(\'Resuming operation of tournament \"{TEST_DB}\""
    assert resp.text.find(err_msg) > -1

    soup = BeautifulSoup(resp.text, 'html.parser')
    validate_view(soup, View.PLAYOFFS)
    validate_stage(soup, TournStage.SEMIS_BRACKET)

    form = soup.select_one('form.actions[action="playoffs"]')
    validate_button(form, "tabulate_semis_results", False)
    validate_button(form, "tabulate_finals_results", False)
