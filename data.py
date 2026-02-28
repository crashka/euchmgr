# -*- coding: utf-8 -*-

"""Blueprint for data ajax requests

NOTE: currently includes data layout information (but need to refactor/reconcile data with
view management).
"""
from ckautils import typecast
from peewee import IntegrityError
from flask import Blueprint, g, request

from security import login_required
from schema import Bracket, TournStage, TournInfo
from euchmgr import compute_player_ranks, compute_team_ranks, compute_playoff_ranks
from ui_schema import Player, PartnerPick, SeedGame, Team, TournGame, PlayoffGame

###################
# blueprint stuff #
###################

data = Blueprint('data', __name__)

# magic strings
HIDDEN   = 'hidden'
CENTERED = 'centered'
EDITABLE = 'editable'

Layout = list[tuple[str, str, str]]

# error string/message tuples
MISSING_FORM_FIELDS = ("'NoneType' object has no attribute 'lstrip'",
                       "Missing field(s) in form data")

##########
# /tourn #
##########

# note that the 'tourn' view does not have a datatable grid, so these routes are purely in
# support of the api (and possibly custom view logic, later), and there is no layout here
tn_upd_flds = {'dates', 'venue'}

@data.get("/tourn/data")
@login_required
def get_tourn() -> dict:
    """Return the data for the current tournament as a single JSON object (unlike the
    other GET methods in this module, which return lists).
    """
    tourn = TournInfo.get()
    tn_data = tourn.tourn_data
    return ajax_data(tn_data)

@data.post("/tourn/data")
@login_required
def post_tourn() -> dict:
    """Update TournInfo data.
    """
    data = request.form
    tourn = TournInfo.get()
    tn_data = None

    try:
        upd_info = {k: typecast(data.get(k)) for k in tn_upd_flds}
        if typecast(data.get('id')) != tourn.id:
            ajax_error("Invalid 'id' specified")
        for col, val in upd_info.items():
            setattr(tourn, col, val)
        mod = tourn.save()
        if mod:
            tn_data = tourn.tourn_data
    except AttributeError as e:
        if str(e) == MISSING_FORM_FIELDS[0]:
            return ajax_error(MISSING_FORM_FIELDS[1])
        raise

    return ajax_data(tn_data)

############
# /players #
############

pl_addl_props = [
    'display_name',
    'champ',
    'seed_win_pct_str',
    'seed_pts_pct_str'
]

pl_layout = [
    ('id',               "ID",          HIDDEN),
    ('display_name',     "Person Name", None),
    ('player_num',       "Player Num",  EDITABLE),
    ('nick_name',        "Player Name", EDITABLE),
    ('champ',            "Champ?",      CENTERED),
    ('seed_wins',        "Wins",        None),
    ('seed_losses',      "Losses",      None),
    ('seed_win_pct_str', "Win Pct",     None),
    ('seed_pts_for',     "Pts For",     None),
    ('seed_pts_against', "Pts Against", None),
    ('seed_pts_pct_str', "Pts Pct",     None),
    ('player_rank',      "Seed Rank",   None)
]

@data.get("/players/data")
@login_required
def get_players() -> dict:
    """
    """
    pl_iter = Player.iter_players()
    pl_data = []
    for player in pl_iter:
        pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
        pl_data.append(player.player_data | pl_props)

    return ajax_data(pl_data)

@data.post("/players/data")
@login_required
def post_players() -> dict:
    """
    """
    data = request.form
    pl_data = None

    try:
        player = Player[typecast(data.get('id'))]
        upd_info = {x[0]: typecast(data.get(x[0])) for x in pl_layout if x[2] == EDITABLE}
        for col, val in upd_info.items():
            setattr(player, col, val)
        mod = player.save()
        if mod:
            pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
            pl_data = player.player_data | pl_props
    except AttributeError as e:
        if str(e) == MISSING_FORM_FIELDS[0]:
            return ajax_error(MISSING_FORM_FIELDS[1])
        raise
    except TypeError as e:
        return ajax_error("Invalid type specified")
    except (IntegrityError, ValueError) as e:
        if str(e) == "UNIQUE constraint failed: player.player_num":
            return ajax_error("Player Num already in use")
        raise

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
    ('round_num',   "Round",       None),
    ('player_nums', "Player Nums", None),
    ('team1_name',  "Team 1",      None),
    ('team2_name',  "Team 2",      None),
    ('bye_players', "Bye(s)",      None),
    ('team1_pts',   "Team 1 Pts",  EDITABLE),
    ('team2_pts',   "Team 2 Pts",  EDITABLE),
    ('winner',      "Winner",      None)
]

@data.get("/seeding/data")
@login_required
def get_seeding() -> dict:
    """
    """
    sg_iter = SeedGame.iter_games(include_byes=True)
    sg_data = []
    for game in sg_iter:
        sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
        sg_data.append(game.__data__ | sg_props)

    return ajax_data(sg_data)

@data.post("/seeding/data")
@login_required
def post_seeding() -> dict:
    """Post scrores to seeding round game.
    """
    data = request.form
    sg_data = None

    try:
        # TODO: wrap this entire try block in a transaction!!!
        game = SeedGame[typecast(data.get('id'))]
        upd_info = {x[0]: typecast(data.get(x[0])) for x in sg_layout if x[2] == EDITABLE}
        team1_pts = upd_info.pop('team1_pts')
        team2_pts = upd_info.pop('team2_pts')
        assert len(upd_info) == 0
        game.add_scores(team1_pts, team2_pts)
        game.save()

        if game.winner:
            game.update_player_stats()
            game.insert_player_games()
            compute_player_ranks()
            if SeedGame.current_round() == -1:
                TournInfo.mark_stage_complete(TournStage.SEED_RESULTS)
            sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
            sg_data = game.__data__ | sg_props
    except AttributeError as e:
        if str(e) == MISSING_FORM_FIELDS[0]:
            return ajax_error(MISSING_FORM_FIELDS[1])
        raise
    except TypeError as e:
        return ajax_error("Invalid type specified")
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

@data.get("/partners/data")
@login_required
def get_partners() -> dict:
    """Ajax call to load datatable for partners view.
    """
    tourn = TournInfo.get()
    if tourn.stage_compl < TournStage.SEED_RANKS:
        return ajax_data([])

    pt_iter = Player.iter_players(by_rank=True)
    pt_data = []
    for player in pt_iter:
        pt_props = {prop: getattr(player, prop) for prop in pt_addl_props}
        pt_data.append(player.player_data | pt_props)

    return ajax_data(pt_data)

@data.post("/partners/data")
@login_required
def post_partners() -> dict:
    """Handle POST of partner pick data--the entire row is submitted, but we only look at
    the `id` and `picks_info` fields.
    """
    data = request.form
    upd_info = {x[0]: typecast(data.get(x[0])) for x in pt_layout if x[2] == EDITABLE}
    picks_info = upd_info.pop('picks_info')
    assert len(upd_info) == 0

    avail = Player.available_players()
    if len(avail) == 0:
        return ajax_error("No available players to pick")

    player = Player[typecast(data.get('id'))]
    if not player.available:
        return ajax_error(f"Specified pick ({player.name}) already on a team")
    if player != avail[0]:
        return ajax_error(f"Current pick belongs to {avail[0].seed_ident}")

    if isinstance(picks_info, int):
        partner = Player.fetch_by_rank(picks_info)
    elif isinstance(picks_info, str):
        match = list(Player.find_by_name_pfx(picks_info))
        match_av = list(filter(lambda x: x.available, match))
        if len(match_av) > 1:
            av_by_name = sorted(match_av, key=lambda pl: pl.name)
            samples = ', '.join([p.name for p in av_by_name][:2]) + ", etc."
            return ajax_error(f"Multiple matches for name starting with \"{picks_info}\" "
                              f"available ({samples}); please respecify")
        elif len(match_av) == 1:
            partner = match_av.pop()
        elif len(match) > 1:
            by_name = sorted(match, key=lambda pl: pl.name)
            samples = ', '.join([p.name for p in by_name][:2]) + ", etc."
            return ajax_error(f"All matches for name starting with \"{picks_info}\" "
                              f"already on a team ({samples})")
        elif len(match) == 1:
            partner = match.pop()  # will get caught as unavailable, below
        else:
            partner = None
    else:
        return ajax_error(f"Cannot find player identified by \"{picks_info}\"")

    if not partner:
        return ajax_error(f"Player identified by \"{picks_info}\" does not exist")
    if not partner.available:
        return ajax_error(f"Specified pick ({partner.name}) already on a team")
    if partner == player:
        return ajax_error(f"Cannot pick self ({player.name}) as partner")

    # automatic final pick(s) if 2 or 3 teams remain
    assert len(avail) not in (0, 1)
    if len(avail) in (2, 3):
        partners = avail[1:]
        assert partner in partners
        player.pick_partners(*partners)
        player.save(cascade=True)
        avail = []
    else:
        player.pick_partners(partner)
        player.save(cascade=True)
        # TODO: pop or remove both player and partner from `avail`, if we are still going
        # to do something with it!!!

    if PartnerPick.current_round() == -1:
        TournInfo.mark_stage_complete(TournStage.PARTNER_PICK)
    # REVISIT: return available players? (...and if so, by num or seed?)
    return ajax_data('all')

##########
# /teams #
##########

tm_addl_props = [
    'player_nums',
    'tourn_win_pct_str',
    'tourn_pts_pct_str'
]

tm_layout = [
    ('id',                "ID",          HIDDEN),
    ('team_seed',         "Team Seed",   None),
    ('player_nums',       "Player Nums", None),
    ('team_name',         "Team",        None),
    ('div_num',           "Div",         None),
    ('div_seed',          "Div Seed",    None),
    ('tourn_wins',        "Wins",        None),
    ('tourn_losses',      "Losses",      None),
    ('tourn_win_pct_str', "Win Pct",     None),
    ('tourn_pts_for',     "Pts For",     None),
    ('tourn_pts_against', "Pts Against", None),
    ('tourn_pts_pct_str', "Pts Pct",     None),
    ('tourn_rank',        "Team Rank",   None),
    ('div_rank',          "Div Rank",    None),
    ('final_rank',        "Tourn Rank",  None)
]

@data.get("/teams/data")
@login_required
def get_teams() -> dict:
    """
    """
    tm_iter = Team.iter_teams()
    tm_data = []
    for team in tm_iter:
        tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
        tm_data.append(team.team_data | tm_props)

    return ajax_data(tm_data)

@data.post("/teams/data")
@login_required
def post_teams() -> dict:
    """
    """
    data = request.form
    tm_data = None

    try:
        team = Team[typecast(data.get('id'))]
        upd_info = {x[0]: typecast(data.get(x[0])) for x in tm_layout if x[2] == EDITABLE}
        for col, val in upd_info.items():
            setattr(team, col, val)
        team.save()

        # NOTE: no need to update row data for now (LATER, may need this if denorm or
        # derived fields are updated when saving)
        if False:
            tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
            tm_data = team.team_data | tm_props
    except AttributeError as e:
        if str(e) == MISSING_FORM_FIELDS[0]:
            return ajax_error(MISSING_FORM_FIELDS[1])
        raise

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
    ('round_num',  "Round",      None),
    ('team_seeds', "Div Seeds",  None),
    ('team1_name', "Team 1",     None),
    ('team2_name', "Team 2",     None),
    ('bye_team',   "Bye",        None),
    ('team1_pts',  "Team 1 Pts", EDITABLE),
    ('team2_pts',  "Team 2 Pts", EDITABLE),
    ('winner',     "Winner",     None)
]

@data.get("/round_robin/data")
@login_required
def get_round_robin() -> dict:
    """
    """
    tg_iter = TournGame.iter_games(include_byes=True)
    tg_data = []
    for game in tg_iter:
        tg_props = {prop: getattr(game, prop) for prop in tg_addl_props}
        tg_data.append(game.__data__ | tg_props)

    return ajax_data(tg_data)

@data.post("/round_robin/data")
@login_required
def post_round_robin() -> dict:
    """
    """
    data = request.form
    tg_data = None

    try:
        # TODO: wrap this entire try block in a transaction!!!
        game = TournGame[typecast(data.get('id'))]
        upd_info = {x[0]: typecast(data.get(x[0])) for x in tg_layout if x[2] == EDITABLE}
        team1_pts = upd_info.pop('team1_pts')
        team2_pts = upd_info.pop('team2_pts')
        assert len(upd_info) == 0
        game.add_scores(team1_pts, team2_pts)
        game.save()

        if game.winner:
            game.update_team_stats()
            game.insert_team_games()
            compute_team_ranks()
            if TournGame.current_round() == -1:
                TournInfo.mark_stage_complete(TournStage.TOURN_RESULTS)
            tg_props = {prop: getattr(game, prop) for prop in tg_addl_props}
            tg_data = game.__data__ | tg_props
    except AttributeError as e:
        if str(e) == MISSING_FORM_FIELDS[0]:
            return ajax_error(MISSING_FORM_FIELDS[1])
        raise
    except TypeError as e:
        return ajax_error("Invalid type specified")
    except RuntimeError as e:
        return ajax_error(str(e))

    return ajax_data(tg_data)

###############
# /final_four #
###############

ff_addl_props = [
    'playoff_status',
    'playoff_match_rec',
    'playoff_win_rec',
    'playoff_win_pct_str',
    'playoff_pts_pct_str'
]

ff_layout = [
    ('id',                   "ID",           HIDDEN),
    ('tourn_rank',           "Team Rank",    None),
    ('team_name',            "Team",         None),
    ('playoff_status',       "Status",       None),
    ('div_num',              "Div",          None),
    ('div_rank',             "Div Rank",     None),
    ('playoff_match_rec',    "Match W-L",    CENTERED),
    ('playoff_win_rec',      "Game W-L",     CENTERED),
    ('playoff_win_pct_str',  "Win Pct",      None),
    ('playoff_pts_for',      "Pts For",      None),
    ('playoff_pts_against',  "Pts Against",  None),
    ('playoff_pts_pct_str',  "Pts Pct",      None),
    ('playoff_rank',         "Playoff Rank", None)
]

@data.get("/final_four/data")
@login_required
def get_final_four() -> dict:
    """
    """
    ff_iter = Team.iter_playoff_teams(by_rank=True)
    ff_data = []
    for team in ff_iter:
        ff_props = {prop: getattr(team, prop) for prop in ff_addl_props}
        ff_data.append(team.final_four_data | ff_props)

    return ajax_data(ff_data)

@data.post("/final_four/data")
@login_required
def post_final_four() -> dict:
    """
    """
    data = request.form
    ff_data = None

    try:
        team = Team[typecast(data.get('id'))]
        upd_info = {x[0]: typecast(data.get(x[0])) for x in ff_layout if x[2] == EDITABLE}
        for col, val in upd_info.items():
            setattr(team, col, val)
        team.save()

        # NOTE: no need to update row data for now (LATER, may need this if denorm or
        # derived fields are updated when saving)
        if False:
            ff_props = {prop: getattr(team, prop) for prop in ff_addl_props}
            ff_data = team.team_data | ff_props
    except AttributeError as e:
        if str(e) == MISSING_FORM_FIELDS[0]:
            return ajax_error(MISSING_FORM_FIELDS[1])
        raise

    return ajax_data(ff_data)

#############
# /playoffs #
#############

pg_addl_props = [
    'bracket_ident',
    'team_ranks'
]

pg_layout = [
    ('id',            "ID",         HIDDEN),
    ('label',         "Game",       None),
    ('bracket_ident', "Round",      None),
    ('matchup_num',   "Matchup",    None),
    ('round_num',     "Game",       None),
    ('team_ranks',    "Team Ranks", None),
    ('team1_name',    "Team 1",     None),
    ('team2_name',    "Team 2",     None),
    ('team1_pts',     "Team 1 Pts", EDITABLE),
    ('team2_pts',     "Team 2 Pts", EDITABLE),
    ('winner',        "Winner",     None)
]

@data.get("/playoffs/data")
@login_required
def get_playoffs() -> dict:
    """
    """
    pg_iter = PlayoffGame.iter_games()
    pg_data = []
    for game in pg_iter:
        pg_props = {prop: getattr(game, prop) for prop in pg_addl_props}
        pg_data.append(game.__data__ | pg_props)

    return ajax_data(pg_data)

@data.post("/playoffs/data")
@login_required
def post_playoffs() -> dict:
    """
    """
    data = request.form
    pg_data = None

    try:
        # TODO: wrap this entire try block in a transaction!!!
        game = PlayoffGame[typecast(data.get('id'))]
        upd_info = {x[0]: typecast(data.get(x[0])) for x in pg_layout if x[2] == EDITABLE}
        team1_pts = upd_info.pop('team1_pts')
        team2_pts = upd_info.pop('team2_pts')
        assert len(upd_info) == 0
        game.add_scores(team1_pts, team2_pts)
        game.save()

        if game.winner:
            game.update_team_stats()
            #game.insert_team_games()

            # NOTE that we don't automatically finalize the playoff ranks when the bracket
            # is complete, since the workflow (currently) requires the tabulation to be
            # manually initiated by the admin.  This same principle applies to seeding,
            # partner pick, and round robin updates (all above).
            compute_playoff_ranks(game.bracket)
            # KINDA HOKEY: we are hard-coding the names of the buttons here (because this
            # feature is too cool not to wire up right now)--LATER, we should really make
            # button identification more symbolic!  See associated comments in admin.html.
            enable_button = None
            if PlayoffGame.bracket_complete(game.bracket):
                if game.bracket == Bracket.SEMIS:
                    TournInfo.mark_stage_complete(TournStage.SEMIS_RESULTS)
                    enable_button = 'tabulate_semis_results'
                else:
                    assert game.bracket == Bracket.FINALS
                    TournInfo.mark_stage_complete(TournStage.FINALS_RESULTS)
                    enable_button = 'tabulate_finals_results'
            pg_props = {prop: getattr(game, prop) for prop in pg_addl_props}
            if enable_button:
                pg_props['enableButton'] = enable_button
            pg_data = game.__data__ | pg_props
    except AttributeError as e:
        if str(e) == MISSING_FORM_FIELDS[0]:
            return ajax_error(MISSING_FORM_FIELDS[1])
        raise
    except TypeError as e:
        return ajax_error("Invalid type specified")
    except RuntimeError as e:
        return ajax_error(str(e))

    return ajax_data(pg_data)

#############
# renderers #
#############

# For now, these "renderers" are specific to this module--LATER, we may want to move them
# to a common layer for all ajax (purely headless) calls, if/when another client structure
# develops.  Note that there are no explicit HTTP status codes nor any notion of rediction
# as part of this interface (only one implicit/hard-wired error code).

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
    # FIX: we currently return this error as HTTP status 200 so that it is handled by
    # `ajax.done()` on the client side--we should really return status 400, so need to
    # figure out how to get the error message to the `ajax.fail()` handler!!!
    return ajax_response(False, msg=err_msg, data=data)

def ajax_response(succ: bool, msg: str = None, data: dict | list | str = None) -> dict:
    """Encapsulate response to an ajax request (GET or POST).  Note that clients can check
    either the `succ` or `err` field to determine the result.  The return `data` is passed
    through to the front-end, with the format being context-dependent (e.g. dict or list
    representing JSON data, or a string directive understood by the client side).

    LATER: we may want to add UI selectors as additional return elements, indicating rows
    and/or cells to highlight, set focus, etc.!!!
    """
    assert succ or msg, "`msg` arg is required for errors"
    if not succ and g.api_call:
        return {
            'succ': succ,
            'err' : msg,
            'info': None,
            'data': data
        }, 400

    # see FIX note in ajax_error() above!
    return {
        'succ': succ,
        'err' : None if succ else msg,
        'info': msg if succ else None,
        'data': data
    }
