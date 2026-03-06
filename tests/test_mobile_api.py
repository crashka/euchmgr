# -*- coding: utf-8 -*-

"""Test mobile API.  As with the admin UI vs. API tests, we don't have to work too hard to
keep this module in sync with the mobile UI test module.  If the two diverge, it should be
for better coverage of areas more pertinent to their respective interfaces and/or clients.
"""

from typing import ClassVar
from collections.abc import Generator
import re
import json

import pytest
from peewee import SqliteDatabase
from flask import Flask
from flask.testing import FlaskClient

from conftest import TestConfig, MobileAPIAppProxy, MobileAPIClient, TEST_DB, restore_stage_db
from test_api import OUT_OF_TURN, PICKER_TAKEN, PICK_TAKEN
from database import db_is_initialized, db_reset, db_connection_context
from schema import TournStage, TournInfo, SeedGame, PlayerGame, PostScore, clear_schema_cache
from euchmgr import prepick_champ_partners
from ui_schema import get_game_by_label
from server import create_app

#####################
# utility functions #
#####################

def post_score_seq(view_path: str, actions: list[tuple]) -> None:
    """Action tuple: (client, refresh, action, score, succ), where `refresh` indicates
    whether the view data should be refreshed before the action, `score` is specified from
    the current client perspective, and `succ` is a bool.  Note that the sequence is
    assumed to end in a successful push (one way or another).

    TODO: need to be able to test post-push actions (which should all fail)!!!
    """
    for client, refresh, action, score, succ in actions:
        if refresh:
            resp = client.get(view_path)
            assert resp.status_code == 200
            api_resp = json.loads(resp.text)
            assert api_resp['succ']
            api_data = api_resp['data']
            client.view_data = api_data
        else:
            if not client.view_data:
                client.view_data = client.view_data_ref.copy()
            api_data = client.view_data

        game_label   = api_data['cur_game']['label']
        player_num   = api_data['user']['player_num']
        team_idx     = api_data['team_idx']
        ref_score_id = api_data['ref_score_id']
        data = {
            'action'       : action,
            'game_label'   : game_label,
            'posted_by_num': player_num,
            'team_idx'     : team_idx,
            'team_pts'     : score[0],
            'opp_pts'      : score[1],
            'ref_score_id' : ref_score_id or ""
        }
        resp = client.post(view_path + '/' + action, data=data)
        assert resp.status_code == 200 if succ else 400
        api_resp = json.loads(resp.text)
        assert api_resp['succ'] == succ

    # this is a little hokey, but variable values in this section are taken from the last
    # loop (assumed to be a successful push)
    with db_connection_context():
        if team_idx == 1:
            score = tuple(reversed(score))
        validate_pushed_score(game_label, score)
        clear_pushed_score(game_label, len(actions))

def validate_pushed_score(label: str, score: tuple[int, int]) -> None:
    """Validate based on assertions.
    """
    game = get_game_by_label(label)
    assert isinstance(game, SeedGame)
    assert game.team1_pts == score[0]
    assert game.team2_pts == score[1]

def clear_pushed_score(label: str, nposts: int) -> None:
    """Reset data associated with the previous post_score sequence.  `nposts` is used for
    additional validation.  NOTE: we do not reset `seed_tb_crit` or `player_rank` since
    there is no clean interface for it, and they don't affect the current set of tests.
    """
    # delete from player_game
    nrows = (PlayerGame
             .delete()
             .where(PlayerGame.game_label == label)
             .execute())
    assert nrows == 4

    # delete from post_score
    nrows = (PostScore
             .delete()
             .where(PostScore.game_label == label)
             .execute())
    assert nrows == nposts

    # revert player stats
    game = get_game_by_label(label)
    assert isinstance(game, SeedGame)
    nrows = game.update_player_stats(revert=True)
    assert nrows == 4

    # revert game score
    game.team1_pts = None
    game.team2_pts = None
    game.winner = None
    nrows = game.save()
    assert nrows == 1

############
# fixtures #
############

@pytest.fixture(scope="module")
def mobile_api_app() -> Generator[Flask]:
    """Class-level app instantiation.
    """
    app = create_app(TestConfig)
    app.wsgi_app = MobileAPIAppProxy(app.wsgi_app)
    app.testing = True
    yield app

@pytest.fixture(scope="class")
def mobile_api_client(mobile_api_app) -> Generator[FlaskClient]:
    """Class-level client instance.
    """
    app = mobile_api_app
    app.test_client_class = MobileAPIClient
    yield app.test_client()

@pytest.fixture(scope="class")
def mobile_api_client2(mobile_api_app) -> Generator[FlaskClient]:
    """Class-level client instance (second instance).
    """
    app = mobile_api_app
    app.test_client_class = MobileAPIClient
    yield app.test_client()

@pytest.fixture(scope="class")
def mobile_api_client3(mobile_api_app) -> Generator[FlaskClient]:
    """Class-level client instance (second instance).
    """
    app = mobile_api_app
    app.test_client_class = MobileAPIClient
    yield app.test_client()

@pytest.fixture(scope="class")
def register_db() -> Generator[SqliteDatabase]:
    """TournStage.PLAYER_ROSTER
    """
    db = restore_stage_db(TournStage(2))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture(scope="class")
def seeding_db() -> Generator[SqliteDatabase]:
    """TournStage.SEED_BRACKET
    """
    db = restore_stage_db(TournStage(4))
    yield db
    db_reset(force=True)
    clear_schema_cache()

@pytest.fixture(scope="class")
def partners_db() -> Generator[SqliteDatabase]:
    """TournStage.SEED_RANKS + partner prepick(s) for reigning champs
    """
    db = restore_stage_db(TournStage(7))
    prepick_champ_partners()
    yield db
    db_reset(force=True)
    clear_schema_cache()

################
# test classes #
################

class TestSanity:
    """Do some baseline validation before getting into module tests.
    """
    user: str = "Abs"

    def test_db(self, register_db):
        """Validate database fixture, access and state.
        """
        assert db_is_initialized()
        tourn = TournInfo.get()
        assert tourn.stage_compl == TournStage.PLAYER_ROSTER

    def test_login(self, mobile_api_client, register_db):
        """Validate login functionality (implemented in `conftest`).
        """
        client = mobile_api_client
        assert client.user is None
        assert client.login(self.user)
        assert client.user == self.user

    def test_logout(self, mobile_api_client, register_db):
        """Validate logout functionality (implemented in `conftest`).
        """
        client = mobile_api_client
        assert client.user == self.user
        assert client.logout()
        assert client.user is None

class TestRegister:
    """Various tests on the `register` view.
    """
    view_name: ClassVar[str] = "register"
    view_path: ClassVar[str] = "/register"
    user1    : ClassVar[str] = "DiPesa"  # nick_name == last_name (initially)
    user2    : ClassVar[str] = "Latt"    # nick_name != last_name (initially)

    def test_register_view(self, mobile_api_client, mobile_api_client2, register_db):
        """First user login and validatation of view data.
        """
        client = mobile_api_client
        client.login(self.user1)
        resp = client.get(self.view_path)
        assert resp.status_code == 200

        tourn = TournInfo.get()
        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user1
        assert api_data['tourn']['name'] == tourn.name
        assert api_data['view'] == self.view_name
        assert len(api_data['nums_avail']) == tourn.players
        client.view_data = api_data

    def test_register_view2(self, mobile_api_client, mobile_api_client2, register_db):
        """Repeat previous test with second user, validate both common and user-specific
        data.
        """
        client = mobile_api_client2
        client.login(self.user2)
        resp = client.get(self.view_path)
        assert resp.status_code == 200

        tourn = TournInfo.get()
        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user2
        assert api_data['tourn']['name'] == tourn.name
        assert api_data['view'] == self.view_name
        assert len(api_data['nums_avail']) == tourn.players
        client.view_data = api_data

    def test_register_player(self, mobile_api_client, register_db):
        """Test registration process, including setting of player_num and nick_name, and
        also ability to change (e.g. correct) player_num.
        """
        client = mobile_api_client

        # set player_num and nick_name
        player = client.view_data['user']
        data = {
            'action'    : "register_player",
            'player_id' : player['id'],
            'player_num': 10,
            'nick_name' : "Tony"
        }
        resp = client.post(self.view_path + "/register_player", data=data)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert api_resp['succ']

        # requery data and validate changes
        resp = client.get(self.view_path)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['id'] == data['player_id']
        assert api_data['user']['player_num'] == data['player_num']
        assert api_data['user']['nick_name'] == data['nick_name']
        client.view_data = api_data

        # update player_num
        player = client.view_data['user']
        data = {
            'action'    : "register_player",
            'player_id' : player['id'],
            'player_num': 15,
            'nick_name' : "Tony"
        }
        resp = client.post(self.view_path + "/register_player", data=data)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert api_resp['succ']

        # requery data and validate changes
        resp = client.get(self.view_path)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['id'] == data['player_id']
        assert api_data['user']['player_num'] == data['player_num']
        assert api_data['user']['nick_name'] == data['nick_name']
        client.view_data = api_data

    def test_register_player2(self, mobile_api_client2, register_db):
        """Test registration process for second user, including clearing of nick_name and
        uniqueness enforcement for player_nums.
        """
        client = mobile_api_client2

        # specify duplicate player_num
        player = client.view_data['user']
        data = {
            'action'    : "register_player",
            'player_id' : player['id'],
            'player_num': 15,
            'nick_name' : ""
        }
        resp = client.post(self.view_path + "/register_player", data=data)
        assert resp.status_code == 400
        api_resp = json.loads(resp.text)
        assert not api_resp['succ']
        assert api_resp['err'] == "Player Num already taken"

        # retry, with nick_name cleared out
        data = {
            'action'    : "register_player",
            'player_id' : player['id'],
            'player_num': 20,
            'nick_name' : ""
        }
        resp = client.post(self.view_path + "/register_player", data=data)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert api_resp['succ']

        # requery data and validate changes
        resp = client.get(self.view_path)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['id'] == data['player_id']
        assert api_data['user']['player_num'] == data['player_num']
        assert api_data['user']['nick_name'] == player['last_name']
        client.view_data = api_data

class TestSeeding:
    """Various tests on the `seeding` view.  We will also use this class to provide the
    context for comprehensive testing of post_score scenarios.  The other stage game views
    (round_robin, semifinals, and finals) should only need a few selected spot checks for
    score posting sequences.
    """
    view_name: ClassVar[str] = "seeding"
    view_path: ClassVar[str] = "/seeding"
    user1    : ClassVar[str] = "Rechtin"     # team 1
    user2    : ClassVar[str] = "Silberberg"  # team 1
    user3    : ClassVar[str] = "Shutts"      # team 2

    def test_fixtures(self, seeding_db):
        """Validate fixtures and log in uers.
        """
        assert db_is_initialized()
        tourn = TournInfo.get()
        assert tourn.stage_compl == TournStage.SEED_BRACKET

    def test_seeding_view(self, mobile_api_client, mobile_api_client2, mobile_api_client3,
                          seeding_db):
        """Log in all users, and validate/cache view data.
        """
        # first user
        client = mobile_api_client
        client.login(self.user1)
        resp = client.get(self.view_path)
        assert resp.status_code == 200

        tourn = TournInfo.get()
        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user1
        assert api_data['tourn']['name'] == tourn.name
        assert api_data['view'] == self.view_name
        assert api_data['cur_game']['team1_name'].startswith(self.user1)
        assert len(api_data['stage_games']) == tourn.seed_rounds
        client.view_data_ref = api_data

        # second user (with abbreviated validation)
        client2 = mobile_api_client2
        client2.login(self.user2)
        resp = client2.get(self.view_path)
        assert resp.status_code == 200

        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user2
        assert api_data['cur_game']['team1_name'].endswith(self.user2)
        client2.view_data_ref = api_data

        # third user (with abbreviated validation)
        client3 = mobile_api_client3
        client3.login(self.user3)
        resp = client3.get(self.view_path)
        assert resp.status_code == 200

        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user3
        assert api_data['cur_game']['team2_name'].startswith(self.user3)
        client3.view_data_ref = api_data

    def test_score_submit(self, mobile_api_client, mobile_api_client3, seeding_db):
        """Sequence:
            - t1 submit
            - t2 accept
        """
        client1 = mobile_api_client
        client3 = mobile_api_client3
        client1.view_data = None
        client3.view_data = None

        actions = [
            (client1, False, "submit_score", (10, 7), True),
            (client3, True,  "accept_score", (7, 10), True)
        ]
        post_score_seq(self.view_path, actions)

    def test_score_submit2(self, mobile_api_client, mobile_api_client3, seeding_db):
        """Sequence:
            - t1 submit
            - t2 submit (matched)
        """
        client1 = mobile_api_client
        client3 = mobile_api_client3
        client1.view_data = None
        client3.view_data = None

        actions = [
            (client1, False, "submit_score", (10, 7), True),
            (client3, False, "submit_score", (7, 10), True)
        ]
        post_score_seq(self.view_path, actions)

    def test_score_submit3(self, mobile_api_client, mobile_api_client3, seeding_db):
        """Sequence:
            - t1 submit
            - t2 correct
            - t1 accept
        """
        client1 = mobile_api_client
        client3 = mobile_api_client3
        client1.view_data = None
        client3.view_data = None

        actions = [
            (client1, False, "submit_score",  (10, 7), True),
            (client3, True,  "correct_score", (8, 10), True),
            (client1, True,  "accept_score",  (10, 8), True)
        ]
        post_score_seq(self.view_path, actions)

    def test_score_submit4(self, mobile_api_client, mobile_api_client3, seeding_db):
        """Sequence:
            - t1 submit
            - t2 submit (mismatched)
            - t2 correct
            - t1 accept
        """
        client1 = mobile_api_client
        client3 = mobile_api_client3
        client1.view_data = None
        client3.view_data = None

        actions = [
            (client1, False, "submit_score",  (10, 7), True),
            (client3, False, "submit_score",  (8, 10), False),
            (client3, True,  "correct_score", (8, 10), True),
            (client1, True,  "accept_score",  (10, 8), True)
        ]
        post_score_seq(self.view_path, actions)

    """
    Additional scenarios to cover:
     - submit
        - duplicate submission from partner
        - mismatched submission from partner
        - intervening correction from partner (matched)
        - intervening correction from partner (mismatched)
        - intervening correction from opponent (matched)
        - intervening correction from opponent (mismatched)
        - intervening acceptance
     - accept
        - intervening acceptance
        - intervenine correction from partner (changed score)
        - intervenine correction from partner (unchanged score)
        - intervenine correction from opponent (changed score)
        - intervenine correction from opponent (unchanged score)
     - correct
        - intervening acceptance
        - intervenine correction from partner (matched)
        - intervenine correction from partner (mismatched)
        - intervenine correction from opponent (matched)
        - intervenine correction from opponent (mismatched)
    """

class TestPartners:
    """Various tests on the `partners` view.

    Test cases:
     - pick out of order (p3 picks p2)
     - picker already taken (p5 picks p2)
     - picker already taken (p6 picks p2)
     - pick already taken (p1 picks p5)
     - pick already taken (p1 picks p6)
     - pick by rank (p1 picks p2)
     - pick by name prefix already taken (p3 picks p1 by name)
     - pick by name prefix already taken (p3 picks p2 by name)
     - pick by name prefix (p3 picks p4 by name)

    Error patterns: OUT_OF_TURN, PICKER_TAKEN, PICK_TAKEN
    """
    view_name : ClassVar[str] = "partners"
    view_path : ClassVar[str] = "/partners"
    user1     : ClassVar[str] = "Shutts"  # rank 1
    user2     : ClassVar[str] = "Fields"  # rank 2
    user3     : ClassVar[str] = "Rooze"   # rank 3
    user10_num: ClassVar[int] = 3         # rank 10 - "Pound"
    user11_num: ClassVar[int] = 26        # rank 11 - "Chisholm"

    def test_fixtures(self, partners_db):
        """Validate fixtures and log in uers.
        """
        assert db_is_initialized()
        tourn = TournInfo.get()
        assert tourn.stage_compl == TournStage.SEED_RANKS

    def test_partners_view(self, mobile_api_client, mobile_api_client2, mobile_api_client3,
                           partners_db):
        """Log in all users, and validate/cache view data.
        """
        # first user
        client = mobile_api_client
        client.login(self.user1)
        resp = client.get(self.view_path)
        assert resp.status_code == 200

        tourn = TournInfo.get()
        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user1
        assert api_data['tourn']['name'] == tourn.name
        assert api_data['view'] == self.view_name
        prepick = api_data['partner_picks'][0]
        prepick_partners = 2 if prepick['partner2'] else 1
        assert len(api_data['partner_picks']) == tourn.players - prepick_partners
        assert len(api_data['picks_avail']) == tourn.players - prepick_partners - 2
        client.view_data = api_data

        # second user (with abbreviated validation)
        client2 = mobile_api_client2
        client2.login(self.user2)
        resp = client2.get(self.view_path)
        assert resp.status_code == 200

        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user2
        client2.view_data = api_data

        # third user (with abbreviated validation)
        client3 = mobile_api_client3
        client3.login(self.user3)
        resp = client3.get(self.view_path)
        assert resp.status_code == 200

        api_resp = json.loads(resp.text)
        assert api_resp['succ']
        api_data = api_resp['data']
        assert api_data['user']['nick_name'] == self.user3
        client3.view_data = api_data

    def test_pick_partner(self, mobile_api_client, mobile_api_client2, partners_db):
        """Pick taken out of order.
        """
        client1 = mobile_api_client
        client2 = mobile_api_client2
        player1 = client1.view_data['user']
        player2 = client2.view_data['user']
        data = {
            'action'     : "pick_partner",
            'player_num' : player2['player_num'],
            'partner_num': player1['player_num'],
            'picks_info' : ""
        }
        resp = client2.post(self.view_path + "/pick_partner", data=data)
        assert resp.status_code == 400
        api_resp = json.loads(resp.text)
        assert not api_resp['succ']
        assert re.match(OUT_OF_TURN, api_resp['err'])

    def test_pick_partner2(self, mobile_api_client, mobile_api_client2, partners_db):
        """Pick based on partner_num.
        """
        client1 = mobile_api_client
        client2 = mobile_api_client2
        player1 = client1.view_data['user']
        player2 = client2.view_data['user']
        data = {
            'action'     : "pick_partner",
            'player_num' : player1['player_num'],
            'partner_num': player2['player_num'],
            'picks_info' : ""
        }
        resp = client1.post(self.view_path + "/pick_partner", data=data)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert api_resp['succ']

        # requery data and validate changes
        resp = client1.get(self.view_path)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['player_num'] == data['player_num']
        assert api_data['user']['partner'] == data['partner_num']
        client1.view_data = api_data

        # validate from picked player perspective
        resp = client2.get(self.view_path)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['player_num'] == data['partner_num']
        assert api_data['user']['picked_by'] == data['player_num']
        assert not api_data['user']['partner']
        client2.view_data = api_data

    def test_pick_partner3(self, mobile_api_client, partners_db):
        """Picker already on a team (previous picker).
        """
        client = mobile_api_client
        player = client.view_data['user']
        data = {
            'action'     : "pick_partner",
            'player_num' : player['player_num'],
            'partner_num': self.user10_num,
            'picks_info' : ""
        }
        resp = client.post(self.view_path + "/pick_partner", data=data)
        assert resp.status_code == 400
        api_resp = json.loads(resp.text)
        assert not api_resp['succ']
        assert re.match(PICKER_TAKEN, api_resp['err'])

    def test_pick_partner4(self, mobile_api_client2, partners_db):
        """Picker already on a team (previously picked).
        """
        client = mobile_api_client2
        player = client.view_data['user']
        data = {
            'action'     : "pick_partner",
            'player_num' : player['player_num'],
            'partner_num': self.user10_num,
            'picks_info' : ""
        }
        resp = client.post(self.view_path + "/pick_partner", data=data)
        assert resp.status_code == 400
        api_resp = json.loads(resp.text)
        assert not api_resp['succ']
        assert re.match(PICKER_TAKEN, api_resp['err'])

    def test_pick_partner5(self, mobile_api_client, mobile_api_client3, partners_db):
        """Pick already on a team (previous picker).
        """
        client1 = mobile_api_client
        client3 = mobile_api_client3
        player1 = client1.view_data['user']
        player3 = client3.view_data['user']
        data = {
            'action'     : "pick_partner",
            'player_num' : player3['player_num'],
            'partner_num': player1['player_num'],
            'picks_info' : ""
        }
        resp = client3.post(self.view_path + "/pick_partner", data=data)
        assert resp.status_code == 400
        api_resp = json.loads(resp.text)
        assert not api_resp['succ']
        assert re.match(PICK_TAKEN, api_resp['err'])

    def test_pick_partner6(self, mobile_api_client2, mobile_api_client3, partners_db):
        """Pick already on a team (previously picked).
        """
        client2 = mobile_api_client2
        client3 = mobile_api_client3
        player2 = client2.view_data['user']
        player3 = client3.view_data['user']
        data = {
            'action'     : "pick_partner",
            'player_num' : player3['player_num'],
            'partner_num': player2['player_num'],
            'picks_info' : ""
        }
        resp = client3.post(self.view_path + "/pick_partner", data=data)
        assert resp.status_code == 400
        api_resp = json.loads(resp.text)
        assert not api_resp['succ']
        assert re.match(PICK_TAKEN, api_resp['err'])

    def test_pick_partner7(self, mobile_api_client3, partners_db):
        """Pick based on picks_info (rank).
        """
        client = mobile_api_client3
        player = client.view_data['user']
        data = {
            'action'     : "pick_partner",
            'player_num' : player['player_num'],
            'partner_num': "",
            'picks_info' : "10"  # rank
        }
        resp = client.post(self.view_path + "/pick_partner", data=data)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert api_resp['succ']

        # requery data and validate changes
        resp = client.get(self.view_path)
        assert resp.status_code == 200
        api_resp = json.loads(resp.text)
        assert isinstance(api_resp['data'], dict)
        api_data = api_resp['data']
        assert api_data['user']['player_num'] == data['player_num']
        assert api_data['user']['partner'] == self.user10_num
        client.view_data = api_data
