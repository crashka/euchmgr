# -*- coding: utf-8 -*-

"""Blueprint for data ajax requests

NOTE: currently includes data layout information (but need to refactor/reconcile data with
view management).
"""
from ckautils import typecast
from peewee import IntegrityError
from flask import Blueprint, request

from schema import TournInfo, Player, SeedGame, Team, TournGame

###################
# blueprint stuff #
###################

data = Blueprint('data', __name__)

# magic strings
CHECKED  = ' checked'
DISABLED = ' disabled'
HIDDEN   = 'hidden'
CENTERED = 'centered'
EDITABLE = 'editable'

############
# /players #
############

pl_addl_props = [
    'full_name',
    'champ'
]

pl_layout = [
    ('id',               "ID",           HIDDEN),
    ('full_name',        "Player",       None),
    ('player_num',       "Player Num",   EDITABLE),
    ('nick_name',        "Short Name",   None),
    ('champ',            "Champ?",       CENTERED),
    ('seed_wins',        "Seed Wins",    None),
    ('seed_losses',      "Seed Losses",  None),
    ('seed_pts_for',     "Seed Pts",     None),
    ('seed_pts_against', "Seed Opp Pts", None),
    ('player_rank',      "Seed Rank",    None)
]

@data.get("/players")
def get_players() -> dict:
    """
    """
    pl_iter = Player.iter_players()
    pl_data = []
    for player in pl_iter:
        pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
        pl_data.append(player.player_data | pl_props)

    return ajax_data(pl_data)

@data.post("/players")
def post_players() -> dict:
    """
    """
    pl_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in pl_layout if x[2] == EDITABLE}
    try:
        player = Player[data['id']]
        for col, val in upd_info.items():
            setattr(player, col, val)
        player.save()

        # NOTE: no need to update row data for now (LATER, may need this if denorm or
        # derived fields are updated when saving)
        if False:
            pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
            pl_data = player.__data__ | pl_props
    except IntegrityError as e:
        return ajax_error(str(e))

    return ajax_data(pl_data)

############
# /seeding #
############

sg_addl_props = [
    'player_nums'
]

sg_layout = [
    ('id',          "ID",          HIDDEN),
    ('label',       "Game",        None),
    ('round_num',   "Rnd",         None),
    ('player_nums', "Player Nums", None),
    ('team1_name',  "Team 1",      None),
    ('team2_name',  "Team 2",      None),
    ('bye_players', "Bye(s)",      None),
    ('team1_pts',   "Team 1 Pts",  EDITABLE),
    ('team2_pts',   "Team 2 Pts",  EDITABLE),
    ('winner',      "Winner",      None)
]

@data.get("/seeding")
def get_seeding() -> dict:
    """
    """
    sg_iter = SeedGame.iter_games(True)
    sg_data = []
    for game in sg_iter:
        sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
        sg_data.append(game.__data__ | sg_props)

    return ajax_data(sg_data)

@data.post("/seeding")
def post_seeding() -> dict:
    """Post scrores to seeding round game.
    """
    sg_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in sg_layout if x[2] == EDITABLE}
    team1_pts = upd_info.pop('team1_pts')
    team2_pts = upd_info.pop('team2_pts')
    assert len(upd_info) == 0
    try:
        # TODO: wrap this entire try block in a transaction!!!
        game = SeedGame[data['id']]
        game.add_scores(team1_pts, team2_pts)
        game.save()

        if game.winner:
            game.update_player_stats()
            game.insert_player_games()
            sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
            sg_data = game.__data__ | sg_props
    except RuntimeError as e:
        return ajax_error(str(e))

    return ajax_data(sg_data)

#############
# /partners #
#############

pt_addl_props = [
    'full_name',
    'seed_ident',
    'champ',
    'available',
    'picks_info',
    'picked_by_info'
]

pt_layout = [
    ('id',             "ID",         HIDDEN),
    ('player_rank',    "Seed Rank",  None),
    ('full_name',      "Player",     None),
    ('player_num',     "Player Num", None),
    ('seed_ident',     "Pick Order", None),
    ('champ',          "Champ?",     CENTERED),
    ('available',      "Avail?",     CENTERED),
    ('picks_info',     "Partner(s) (pick by Name or Rank)", EDITABLE),
    ('picked_by_info', "Picked By",  None)
]

@data.get("/partners")
def get_partners() -> dict:
    """Ajax call to load datatable for partners view.
    """
    pt_iter = Player.iter_players(by_rank=True)
    pt_data = []
    for player in pt_iter:
        pt_props = {prop: getattr(player, prop) for prop in pt_addl_props}
        pt_data.append(player.__data__ | pt_props)

    return ajax_data(pt_data)

@data.post("/partners")
def post_partners() -> dict:
    """Handle POST of partner pick data--the entire row is submitted, but we only look at
    the `id` and `picks_info` fields.
    """
    pt_err = None
    pt_upd = False

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in pt_layout if x[2] == EDITABLE}
    picks_info = upd_info.pop('picks_info')
    assert len(upd_info) == 0

    avail = Player.available_players(requery=True)
    if len(avail) == 0:
        return ajax_error("No available players to pick")

    player = Player[typecast(data['id'])]
    if not player.available:
        return ajax_error(f"Invalid selection; current player ({player.nick_name}) already on a team")
    if player != avail[0]:
        return ajax_error(f"Selection out of turn; active pick belongs to {avail[0].seed_ident}")

    if isinstance(picks_info, int):
        partner = Player.fetch_by_rank(picks_info)
    elif isinstance(picks_info, str):
        match = list(Player.find_by_name_pfx(picks_info))
        match_av = list(filter(lambda x: x.available, match))
        if len(match_av) > 1:
            av_by_name = sorted(match_av, key=lambda pl: pl.nick_name)
            samples = ', '.join([p.nick_name for p in av_by_name][:2]) + ", etc."
            return ajax_error(f"Multiple available matches found for name starting with \"{picks_info}\" ({samples}); please respecify pick")
        elif len(match_av) == 1:
            partner = match_av.pop()
        elif len(match) > 1:
            by_name = sorted(match, key=lambda pl: pl.nick_name)
            samples = ', '.join([p.nick_name for p in by_name][:2]) + ", etc."
            return ajax_error(f"All matches for name starting with \"{picks_info}\" ({samples}) already on a team")
        elif len(match) == 1:
            partner = match.pop()  # will get caught as unavailable, below
        else:
            partner = None
    else:
        return ajax_error(f"Cannot find player identified by \"{picks_info}\"")

    if not partner:
        return ajax_error(f"Player identified by \"{picks_info}\" does not exist")
    if not partner.available:
        return ajax_error(f"Specified pick ({partner.nick_name}) already on a team")
    if partner == player:
        return ajax_error(f"Cannot pick self ({player.nick_name}) as partner")

    # automatic final pick(s) if 2 or 3 teams remain
    assert len(avail) not in (0, 1)
    if len(avail) in (2, 3):
        partners = avail[1:]
        assert partner in partners
        player.pick_partners(*partners)
        player.save()
        avail = []
        pt_upd = True
    else:
        player.pick_partners(partner)
        player.save()
        pt_upd = True

    # REVISIT: return available players? (...and if so, by num or seed?)
    return ajax_data('all')

##########
# /teams #
##########

tm_addl_props = [
    'player_nums'
]

tm_layout = [
    ('id',                "ID",            HIDDEN),
    ('team_seed',         "Team Seed",     None),
    ('player_nums',       "Player Nums",   None),
    ('team_name',         "Team",          None),
    ('div_num',           "Div",           None),
    ('div_seed',          "Div Seed",      None),
    ('tourn_wins',        "Tourn Wins",    None),
    ('tourn_losses',      "Tourn Losses",  None),
    ('tourn_pts_for',     "Tourn Pts",     None),
    ('tourn_pts_against', "Tourn Opp Pts", None),
    ('tourn_rank',        "Tourn Rank",    None),
    ('div_rank',          "Div Rank",      None)
]

@data.get("/teams")
def get_teams() -> dict:
    """
    """
    tm_iter = Team.iter_teams()
    tm_data = []
    for team in tm_iter:
        tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
        tm_data.append(team.team_data | tm_props)

    return ajax_data(tm_data)

@data.post("/teams")
def post_teams() -> dict:
    """
    """
    tm_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in tm_layout if x[2] == EDITABLE}
    try:
        team = Team[data['id']]
        for col, val in upd_info.items():
            setattr(team, col, val)
        team.save()

        # NOTE: no need to update row data for now (LATER, may need this if denorm or
        # derived fields are updated when saving)
        if False:
            tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
            tm_data = team.__data__ | tm_props
    except IntegrityError as e:
        return ajax_error(str(e))

    return ajax_data(tm_data)

################
# /round_robin #
################

tg_addl_props = [
    'team_seeds'
]

tg_layout = [
    ('id',         "ID",         HIDDEN),
    ('label',      "Game",       None),
    ('div_num',    "Div",        None),
    ('round_num',  "Rnd",        None),
    ('team_seeds', "Div Seeds",  None),
    ('team1_name', "Team 1",     None),
    ('team2_name', "Team 2",     None),
    ('bye_team',   "Bye",        None),
    ('team1_pts',  "Team 1 Pts", EDITABLE),
    ('team2_pts',  "Team 2 Pts", EDITABLE),
    ('winner',     "Winner",     None)
]

@data.get("/round_robin")
def get_round_robin() -> dict:
    """
    """
    tg_iter = TournGame.iter_games(True)
    tg_data = []
    for game in tg_iter:
        tg_props = {prop: getattr(game, prop) for prop in tg_addl_props}
        tg_data.append(game.__data__ | tg_props)

    return ajax_data(tg_data)

@data.post("/round_robin")
def post_round_robin() -> dict:
    """
    """
    tg_data = None

    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in tg_layout if x[2] == EDITABLE}
    team1_pts = upd_info.pop('team1_pts')
    team2_pts = upd_info.pop('team2_pts')
    assert len(upd_info) == 0
    try:
        # TODO: wrap this entire try block in a transaction!!!
        game = TournGame[data['id']]
        game.add_scores(team1_pts, team2_pts)
        game.save()

        if game.winner:
            game.update_team_stats()
            game.insert_team_games()
            tg_props = {prop: getattr(game, prop) for prop in tg_addl_props}
            tg_data = game.__data__ | tg_props
    except RuntimeError as e:
        return ajax_error(str(e))

    return ajax_data(tg_data)

#############
# renderers #
#############

def ajax_data(data: dict | list | str) -> dict:
    """Wrapper for returning specified data in the structure expected by DataTables for an
    ajax data source.  `data` must be specified.
    """
    return ajax_response(True, data=data)

def ajax_succ(info_msg: str = None, data: dict | list | str = None) -> dict:
    """Convenience function (slightly shorter).  `info_msg` is optional.
    """
    return ajax_response(True, msg=info_msg, data=data)

def ajax_error(err_msg: str, data: dict | list | str = None) -> dict:
    """Convenience function (slightly shorter).  `err_msg` must be specified.
    """
    return ajax_response(False, msg=err_msg, data=data)

# type aliases
RowSelector = str

def ajax_response(succ: bool, msg: str = None, data: dict | list | str = None) -> dict:
    """Encapsulate response to an ajax request (GET or POST).  Note that clients can check
    either the `succ` or `err` field to determine the result.  The return `data` is passed
    through to the front-end, with the format being context-dependent (e.g. dict or list
    representing JSON data, or a string directive understood by the client side).

    LATER: we may want to add UI selectors as additional return elements, indicating rows
    and/or cells to highlight, set focus, etc.!!!
    """
    assert succ or msg, "`msg` arg is required for errors"
    return {
        'succ'   : succ,
        'err'    : None if succ else msg,
        'info'   : msg if succ else None,
        'data'   : data
    }
