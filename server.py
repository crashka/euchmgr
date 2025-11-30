#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Simple frontend for managing euchre tournaments Beta-style

To start the server (local usage only)::

  $ python -m server

or::

  $ flask --app server run [--debug]

To run the application, open a browser window and navigate to ``localhost:5000``.  The
usage of the application should be pretty self-explanatory.

To do list:

"""

from enum import IntEnum
from numbers import Number
from datetime import datetime
from glob import glob
import os.path
import re

from ckautils import typecast
from peewee import OperationalError, IntegrityError
from flask import (Flask, Request, request, session, render_template, Response, abort,
                   redirect, url_for)
from flask_session import Session
from cachelib.file import FileSystemCache
from werkzeug.utils import secure_filename

from core import DATA_DIR, UPLOAD_DIR, ImplementationError
from database import DB_FILETYPE, now_str
from schema import (GAME_PTS, TournStage, TournInfo, Player, SeedGame, Team, TournGame,
                    PlayerGame, TeamGame)
from euchmgr import (db_init, tourn_create, upload_roster, generate_player_nums,
                     build_seed_bracket, fake_seed_games, validate_seed_round,
                     compute_player_seeds, prepick_champ_partners, fake_pick_partners,
                     build_tourn_teams, compute_team_seeds, build_tourn_bracket,
                     fake_tourn_games, validate_tourn, compute_team_ranks)

#############
# app stuff #
#############

app = Flask(__name__)

SESSION_TYPE = 'cachelib'
SESSION_CACHELIB = FileSystemCache(cache_dir="sessions", default_timeout=0)
app.config.from_object(__name__)
Session(app)

APP_NAME       = "Euchre Manager"
APP_TEMPLATE   = "euchmgr.html"
CHART_TEMPLATE = "chart.html"
DASH_TEMPLATE  = "dash.html"
SD_BRACKET     = "Seeding Round Bracket"
SD_SCORES      = "Seeding Round Scores"
RR_BRACKETS    = "Round Robin Brackets"
RR_SCORES      = "Round Robin Scores"
SD_DASH        = "Seeding Round Live Dashboard"
RR_DASH        = "Round Robin Live Dashboard"

# magic strings
CHECKED  = ' checked'
DISABLED = ' disabled'
HIDDEN   = 'hidden'
CENTERED = 'centered'
EDITABLE = 'editable'

# app views
class View(IntEnum):
    PLAYERS     = 0
    SEEDING     = 1
    PARTNERS    = 2
    TEAMS       = 3
    ROUND_ROBIN = 4


VIEW_NAME = [
    'Players',
    'Seeding Round',
    'Picking Partners',
    'Teams',
    'Round Robin'
]

###############
# tourn stuff #
###############

# key = input name; value = default (form input domain, i.e. string representation), if
# `form.get(param) is None`
TOURN_PARAMS = {
    'players'  : 'null',
    'teams'    : 'null',
    'thm_teams': 'null'
}

def get_tourns() -> list[str]:
    """Get list of existing tournaments (currently based on existence of database file in
    DATA_DIR--later, we can do something more structured)
    """
    glob_str  = os.path.join(DATA_DIR, r'*' + DB_FILETYPE)
    match_str = os.path.join(DATA_DIR, r'(.+)' + DB_FILETYPE)

    tourns = []
    for file in glob(glob_str):
        m = re.fullmatch(match_str, file)
        assert m and len(m.groups()) == 1
        tourns.append(m.groups()[0])

    return sorted(tourns)

#################
# utility stuff #
#################

FLOAT_PREC = 1

def round_val(val: Number) -> Number:
    """Provide the appropriate level of rounding for the leaderboard or stat value (does
    not change the number type); passthrough for non-numeric types (e.g. bool or str)
    """
    if isinstance(val, float):
        return round(val, FLOAT_PREC)
    return val

# do not downcase the rest of the string like str.capitalize()
cap_first = lambda x: x[0].upper() + x[1:]

def fmt_score(pts: int, prev_pts: int = -1) -> str:
    """Markup score if game-winning (bold) and/or changed from prev (em)
    """
    # special case for byes
    if pts == -1:
        return '-'

    ret = str(pts)
    if pts >= GAME_PTS:
        ret = f"<b>{ret}</b>"

    if prev_pts != -1 and pts != prev_pts:
        assert pts >= (prev_pts or 0)
        ret = f"<em>{ret}</em>"

    return ret

def fmt_tally(pts: int) -> str:
    """Print arguments for <img> tag for showing point tallies
    """
    if pts == 0:
        return ''
    tally_file = f"/static/tally_{pts}.png"
    return f'src="{tally_file}" height="15" width="50"'

################
# Flask Routes #
################

SUBMIT_FUNCS = [
    'create_tourn',
    'update_tourn',
    'gen_player_nums',
    'gen_seed_bracket',
    'fake_seed_results',
    'tabulate_seed_results',
    'fake_partner_picks',
    'comp_team_seeds',
    'gen_tourn_brackets',
    'fake_tourn_results',
    'tabulate_tourn_results'
]

STAGE_MAPPING = [
    (TournStage.TEAM_RANKS,    View.TEAMS),
    (TournStage.TOURN_RESULTS, View.ROUND_ROBIN),
    (TournStage.TEAM_SEEDS,    View.TEAMS),
    (TournStage.PARTNER_PICK,  View.PARTNERS),
    (TournStage.SEED_RESULTS,  View.SEEDING),
    (TournStage.PLAYER_NUMS,   View.PLAYERS),
]

def dflt_view(tourn: TournInfo) -> View:
    """Return most relevant view for the current stage of the tournament
    """
    if tourn.stage_start is None:
        return None
    for stage, view in STAGE_MAPPING:
        if tourn.stage_start >= stage:
            return view
    return None

@app.get("/")
def index() -> str:
    """
    """
    tourn     = None
    new_tourn = None
    view      = None

    tourn_name = request.args.get('tourn')
    if tourn_name:
        db_init(tourn_name)
        if tourn_name == SEL_NEW:
            tourn = TournInfo()
            new_tourn = True
        else:
            tourn = TournInfo.get()
            new_tourn = False

    if 'view' in request.args:
        view = typecast(request.args['view'])
    elif tourn:
        view = dflt_view(tourn)

    context = {
        'tourn'    : tourn,
        'new_tourn': new_tourn,
        'view'     : view
    }
    return render_app(context)

@app.post("/")
def submit() -> str:
    """Process submitted form, switch on ``submit_func``, which is validated against
    values in ``SUBMIT_FUNCS``
    """
    func = request.form['submit_func']
    if func not in SUBMIT_FUNCS:
        abort(404, f"Invalid submit func '{func}'")
    return globals()[func](request.form)

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
    ('player_seed',      "Seed Rank",    None)
]

@app.get("/players")
def get_players() -> dict:
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    pl_iter = Player.iter_players()
    pl_data = []
    for player in pl_iter:
        pl_props = {prop: getattr(player, prop) for prop in pl_addl_props}
        pl_data.append(player.__data__ | pl_props)

    return ajax_data(pl_data)

@app.post("/players")
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

@app.get("/seeding")
def get_seeding() -> dict:
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    sg_iter = SeedGame.iter_games(True)
    sg_data = []
    for game in sg_iter:
        sg_props = {prop: getattr(game, prop) for prop in sg_addl_props}
        sg_data.append(game.__data__ | sg_props)

    return ajax_data(sg_data)

@app.post("/seeding")
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
    ('player_seed',    "Seed Rank",  None),
    ('full_name',      "Player",     None),
    ('player_num',     "Player Num", None),
    ('seed_ident',     "Pick Order", None),
    ('champ',          "Champ?",     CENTERED),
    ('available',      "Avail?",     CENTERED),
    ('picks_info',     "Partner(s) (pick by Name or Rank)", EDITABLE),
    ('picked_by_info', "Picked By",  None)
]

@app.get("/partners")
def get_partners() -> dict:
    """Ajax call to load datatable for partners view.
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    pt_iter = Player.iter_players(by_seeding=True)
    pt_data = []
    for player in pt_iter:
        pt_props = {prop: getattr(player, prop) for prop in pt_addl_props}
        pt_data.append(player.__data__ | pt_props)

    return ajax_data(pt_data)

@app.post("/partners")
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
        partner = Player.fetch_by_seed(picks_info)
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

@app.get("/teams")
def get_teams() -> dict:
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    tm_iter = Team.iter_teams()
    tm_data = []
    for team in tm_iter:
        tm_props = {prop: getattr(team, prop) for prop in tm_addl_props}
        tm_data.append(team.__data__ | tm_props)

    return ajax_data(tm_data)

@app.post("/teams")
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

@app.get("/round_robin")
def get_round_robin() -> dict:
    """
    """
    tourn_name = request.args.get('tourn')

    db_init(tourn_name)
    tg_iter = TournGame.iter_games(True)
    tg_data = []
    for game in tg_iter:
        tg_props = {prop: getattr(game, prop) for prop in tg_addl_props}
        tg_data.append(game.__data__ | tg_props)

    return ajax_data(tg_data)

@app.post("/round_robin")
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

##########
# Charts #
##########

CHART_FUNCS = [
    'sd_bracket',
    'sd_scores',
    'rr_brackets',
    'rr_scores'
]

@app.get("/chart/<path:subpath>")
def get_chart(subpath: str) -> str:
    """Render specified chart
    """
    chart, tourn_name = subpath.split('/', 1)
    if chart not in CHART_FUNCS:
        abort(404, f"Invalid chart func '{chart}'")

    db_init(tourn_name)
    tourn = TournInfo.get()
    return globals()[chart](tourn)

def sd_bracket(tourn: TournInfo) -> str:
    """Render seed round bracket as a chart
    """
    rnd_tables = tourn.players // 4
    rnd_byes = tourn.players % 4

    matchups = {}  # key sequence: rnd, tbl -> matchup_html
    sg_iter = SeedGame.iter_games(include_byes=True)
    for sg in sg_iter:
        rnd = sg.round_num
        tbl = sg.table_num
        if rnd not in matchups:
            matchups[rnd] = {}
        assert tbl not in matchups[rnd]
        if tbl:
            matchups[rnd][tbl] = "<br>vs.<br>".join(sg.team_tags)
        else:
            matchups[rnd][tbl] = "<br>".join(sg.bye_tags)  # bye(s)

    assert len(matchups) == tourn.seed_rounds
    for rnd, tbls in matchups.items():
        assert len(tbls) == rnd_tables + int(bool(rnd_byes))

    context = {
        'chart_num' : 0,
        'title'     : SD_BRACKET,
        'tourn'     : tourn,
        'rnds'      : tourn.seed_rounds,
        'rnd_tables': rnd_tables,
        'rnd_byes'  : rnd_byes,
        'matchups'  : matchups,
        'bold_color': '#555555'
    }
    return render_chart(context)

def sd_scores(tourn: TournInfo) -> str:
    """Render seed round scores as a chart
    """
    pl_list = sorted(Player.iter_players(), key=lambda pl: pl.player_num)
    # sub-dict key is rnd, value is pts
    team_pts = {pl.player_num: {} for pl in pl_list}
    opp_pts  = {pl.player_num: {} for pl in pl_list}
    wins     = {pl.player_num: 0 for pl in pl_list}
    losses   = {pl.player_num: 0 for pl in pl_list}
    pg_iter = PlayerGame.iter_games(include_byes=True)
    for pg in pg_iter:
        pl_num = pg.player_num
        rnd = pg.round_num
        assert rnd not in team_pts[pl_num]
        assert rnd not in opp_pts[pl_num]
        if pg.is_bye:
            team_pts[pl_num][rnd] = None
            opp_pts[pl_num][rnd] = None
        else:
            team_pts[pl_num][rnd] = fmt_score(pg.team_pts)
            opp_pts[pl_num][rnd] = fmt_score(pg.opp_pts)
            if pg.is_winner:
                wins[pl_num] += 1
            else:
                losses[pl_num] += 1

    win_tallies = {}
    loss_tallies = {}
    for pl in pl_list:
        win_tallies[pl.player_num] = fmt_tally(wins[pl.player_num])
        loss_tallies[pl.player_num] = fmt_tally(losses[pl.player_num])

    context = {
        'chart_num'   : 1,
        'title'       : SD_SCORES,
        'tourn'       : tourn,
        'rnds'        : tourn.seed_rounds,
        'players'     : pl_list,
        'team_pts'    : team_pts,
        'opp_pts'     : opp_pts,
        'wins'        : wins,
        'losses'      : losses,
        'win_tallies' : win_tallies,
        'loss_tallies': loss_tallies,
        'round_val'   : round_val,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

def rr_brackets(tourn: TournInfo) -> str:
    """Render round robin brackets as a chart
    """
    div_list   = list(range(1, tourn.divisions + 1))
    div_teams  = (tourn.teams - 1) // tourn.divisions + 1  # counting byes
    tot_byes   = tourn.teams % tourn.divisions
    div_tables = [div_teams // 2] * tourn.divisions
    div_byes   = [0] * tourn.divisions
    for i in range(tot_byes):
        div_tables[-1 - i] -= 1
        div_byes[-1 - i] += 1
    rnd_tables = dict(zip(div_list, div_tables))
    rnd_byes = dict(zip(div_list, div_byes))

    # key sequence for sub-dict: rnd, tbl -> matchup_html
    matchups = {div: {} for div in div_list}
    tg_iter = TournGame.iter_games(include_byes=True)
    for tg in tg_iter:
        div = tg.div_num
        rnd = tg.round_num
        tbl = tg.table_num
        if rnd not in matchups[div]:
            matchups[div][rnd] = {}
        assert tbl not in matchups[div][rnd]
        if tbl:
            matchups[div][rnd][tbl] = "<br>vs.<br>".join(tg.team_tags)
        else:
            matchups[div][rnd][tbl] = tg.bye_tag

    for div in div_list:
        assert len(matchups[div]) == tourn.tourn_rounds
        for rnd, tbls in matchups[div].items():
            assert len(tbls) == rnd_tables[div] + rnd_byes[div]

    context = {
        'chart_num' : 2,
        'title'     : RR_BRACKETS,
        'tourn'     : tourn,
        'rnds'      : tourn.tourn_rounds,
        'div_list'  : div_list,
        'rnd_tables': rnd_tables,
        'rnd_byes'  : rnd_byes,
        'matchups'  : matchups,
        'bold_color': '#555555'
    }
    return render_chart(context)

def rr_scores(tourn: TournInfo) -> str:
    """Render round robin scores as a chart
    """
    div_list = list(range(1, tourn.divisions + 1))
    tm_list  = sorted(Team.iter_teams(), key=lambda tm: tm.team_seed)
    team_pts = {}
    opp_pts  = {}
    wins     = {}
    losses   = {}
    for div in div_list:
        # inner dict represents points by round {rnd: pts}
        team_pts[div] = {tm.team_seed: {} for tm in tm_list}
        opp_pts[div]  = {tm.team_seed: {} for tm in tm_list}
        wins[div]     = {tm.team_seed: 0 for tm in tm_list}
        losses[div]   = {tm.team_seed: 0 for tm in tm_list}

    tg_iter = TeamGame.iter_games(include_byes=True)
    for tg in tg_iter:
        div = tg.team.div_num
        tm_seed = tg.team_seed
        assert tm_seed == tg.team.team_seed
        rnd = tg.round_num
        assert rnd not in team_pts[div][tm_seed]
        assert rnd not in opp_pts[div][tm_seed]
        if tg.is_bye:
            team_pts[div][tm_seed][rnd] = None
            opp_pts[div][tm_seed][rnd] = None
        else:
            team_pts[div][tm_seed][rnd] = fmt_score(tg.team_pts)
            opp_pts[div][tm_seed][rnd] = fmt_score(tg.opp_pts)
            if tg.is_winner:
                wins[div][tm_seed] += 1
            else:
                losses[div][tm_seed] += 1

    div_teams = {div: [] for div in div_list}
    win_tallies = {div: {} for div in div_list}
    loss_tallies = {div: {} for div in div_list}
    for div in div_list:
        for tm in tm_list:
            if tm.div_num == div:
                div_teams[div].append(tm)
            win_tallies[div][tm.team_seed] = fmt_tally(wins[div][tm.team_seed])
            loss_tallies[div][tm.team_seed] = fmt_tally(losses[div][tm.team_seed])

    context = {
        'chart_num'   : 3,
        'title'       : RR_SCORES,
        'tourn'       : tourn,
        'rnds'        : tourn.tourn_rounds,
        'div_list'    : div_list,
        'div_teams'   : div_teams,
        'team_pts'    : team_pts,
        'opp_pts'     : opp_pts,
        'wins'        : wins,
        'losses'      : losses,
        'win_tallies' : win_tallies,
        'loss_tallies': loss_tallies,
        'round_val'   : round_val,
        'bold_color'  : '#555555'
    }
    return render_chart(context)

###################
# Live Dashboards #
###################

DASH_FUNCS = [
    'sd_dash',
    'rr_dash'
]

TIME_FMT = '%Y-%m-%d %H:%M:%S'
DFLT_UPDATE_INT = 5900

COLCLS_UP   = 'grn_fg'
COLCLS_DOWN = 'red_fg'

# session storage key
SD_DASH_KEY = 'sd_dash'
RR_DASH_KEY = 'rr_dash'

@app.get("/dash/<path:subpath>")
def get_dash(subpath: str) -> str:
    """Render specified live dashboard
    """
    dash, tourn_name = subpath.split('/', 1)
    if dash not in DASH_FUNCS:
        abort(404, f"Invalid dash func '{dash}'")

    db_init(tourn_name)
    tourn = TournInfo.get(requery=True)
    return globals()[dash](tourn)

def sd_dash(tourn: TournInfo) -> str:
    """Render seed round live dashboard
    """
    pl_list = sorted(Player.iter_players(), key=lambda pl: pl.player_num)
    # sub-dict key is rnd, value is pts
    team_pts = {pl.player_num: {} for pl in pl_list}
    opp_pts  = {pl.player_num: {} for pl in pl_list}
    wins     = {pl.player_num: 0 for pl in pl_list}
    losses   = {pl.player_num: 0 for pl in pl_list}
    pg_iter = PlayerGame.iter_games(include_byes=True)
    for pg in pg_iter:
        pl_num = pg.player_num
        rnd = pg.round_num
        assert rnd not in team_pts[pl_num]
        assert rnd not in opp_pts[pl_num]
        if pg.is_bye:
            team_pts[pl_num][rnd] = None
            opp_pts[pl_num][rnd] = None
        else:
            team_pts[pl_num][rnd] = fmt_score(pg.team_pts)
            opp_pts[pl_num][rnd] = fmt_score(pg.opp_pts)
            if pg.is_winner:
                wins[pl_num] += 1
            else:
                losses[pl_num] += 1

    win_tallies = {}
    loss_tallies = {}
    for pl in pl_list:
        win_tallies[pl.player_num] = fmt_tally(wins[pl.player_num])
        loss_tallies[pl.player_num] = fmt_tally(losses[pl.player_num])

    context = {
        'dash_num'    : 0,
        'title'       : SD_DASH,
        'tourn'       : tourn,
        'rnds'        : tourn.seed_rounds,
        'players'     : pl_list,
        'team_pts'    : team_pts,
        'opp_pts'     : opp_pts,
        'wins'        : wins,
        'losses'      : losses,
        'win_tallies' : win_tallies,
        'loss_tallies': loss_tallies,
        'round_val'   : round_val,
        'bold_color'  : '#555555'
    }
    return render_dash(context)

def rr_dash(tourn: TournInfo) -> str:
    """Render round robin live dashboard
    """
    update_int = DFLT_UPDATE_INT
    done = False

    div_list = list(range(1, tourn.divisions + 1))
    tm_list  = sorted(Team.iter_teams(), key=lambda tm: tm.div_rank or tourn.teams)
    # inner dict represents points by round {rnd: pts}
    team_pts = {tm.team_seed: {} for tm in tm_list}
    opp_pts  = {tm.team_seed: {} for tm in tm_list}
    wins     = {tm.team_seed: 0 for tm in tm_list}
    losses   = {tm.team_seed: 0 for tm in tm_list}
    tot_gms  = 0
    tot_pts  = 0

    tg_list = list(TeamGame.iter_games(include_byes=True))
    not_bye = lambda g: not g.is_bye
    max_rnd = lambda ls: max(g.round_num for g in ls) if ls else 0
    cur_rnd = {div: max_rnd(list(filter(not_bye, tg_list))) for div in div_list}
    for tg in tg_list:
        div = tg.team.div_num
        tm_seed = tg.team_seed
        assert tm_seed == tg.team.team_seed
        rnd = tg.round_num
        assert rnd not in team_pts[tm_seed]
        assert rnd not in opp_pts[tm_seed]
        if not tg.is_bye:
            tot_gms += 1
            tot_pts += tg.team_pts
            team_pts[tm_seed][rnd] = tg.team_pts
            opp_pts[tm_seed][rnd] = tg.opp_pts
            if tg.is_winner:
                wins[tm_seed] += 1
            else:
                losses[tm_seed] += 1
        elif rnd <= cur_rnd[div]:
            team_pts[tm_seed][rnd] = -1
            opp_pts[tm_seed][rnd] = -1

    prev_tot_gms     = 0
    prev_tot_pts     = 0
    prev_team_pts    = {}
    prev_opp_pts     = {}
    prev_pts_for     = {}
    prev_pts_against = {}
    prev_stats       = None
    prev_mvmt        = None
    prev_colcls      = None
    if prev_frame := session.get(RR_DASH_KEY):
        if str(tourn.created_at) > prev_frame['updated']:
            session.pop(RR_DASH_KEY)
        else:
            prev_tot_gms     = prev_frame['tot_gms']
            prev_tot_pts     = prev_frame['tot_pts']
            prev_team_pts    = prev_frame['team_pts']
            prev_opp_pts     = prev_frame['opp_pts']
            prev_pts_for     = prev_frame['pts_for']
            prev_pts_against = prev_frame['pts_against']
            prev_stats       = prev_frame['stats']
            prev_mvmt        = prev_frame['mvmt']
            prev_colcls      = prev_frame['colcls']

    div_teams    = {div: [] for div in div_list}
    # the following are all keyed off of team_seed
    win_tallies  = {}
    loss_tallies = {}
    stats        = {}  # value: (win_pct, pts_diff, rank)
    mvmt         = {}
    colcls       = {}
    # inner dict represents points (formatted!) by round
    pts_for      = {tm.team_seed: {} for tm in tm_list}
    pts_against  = {tm.team_seed: {} for tm in tm_list}
    for tm in tm_list:
        div = tm.div_num
        tm_seed = tm.team_seed
        div_teams[div].append(tm)

        # for now, we always (re-)format win/loss tallies and stats--LATER, need to
        # determine changes to stats for highlighting!!!
        win_tallies[tm_seed] = fmt_tally(wins[tm_seed])
        loss_tallies[tm_seed] = fmt_tally(losses[tm_seed])
        stats[tm_seed] = (
            f"{round_val(tm.tourn_win_pct)}%" if tm.tourn_win_pct is not None else '',
            tm.tourn_pts_diff if tm.tourn_pts_diff is not None else '',
            tm.div_rank or ''
        )

        # conditionally, we either format or reuse string values for pts_for/_agnst, mvmt,
        # colcls
        if prev_stats:
            if tot_pts == prev_tot_pts:
                # use previous values
                pts_for[tm_seed] = prev_pts_for[tm_seed]
                pts_against[tm_seed] = prev_pts_against[tm_seed]
            else:
                # format new values
                for rnd, cur_pts in team_pts[tm_seed].items():
                    prev_pts = prev_team_pts[tm_seed].get(rnd)
                    pts_for[tm_seed][rnd] = fmt_score(cur_pts, prev_pts)

                for rnd, cur_pts in opp_pts[tm_seed].items():
                    prev_pts = prev_opp_pts[tm_seed].get(rnd)
                    pts_against[tm_seed][rnd] = fmt_score(cur_pts, prev_pts)

            if tot_pts == prev_tot_pts and prev_mvmt:
                mvmt[tm_seed] = prev_mvmt.get(tm_seed, '')
                colcls[tm_seed] = prev_colcls.get(tm_seed, '')
            elif prev_stats[tm_seed][2]:
                rank_diff = (prev_stats[tm_seed][2] or 0) - (tm.div_rank or 0)
                if rank_diff > 0:
                    mvmt[tm_seed] = f'+{rank_diff}'
                    colcls[tm_seed] = COLCLS_UP
                elif rank_diff < 0:
                    mvmt[tm_seed] = str(rank_diff)
                    colcls[tm_seed] = COLCLS_DOWN
            if tm_seed not in mvmt:
                mvmt[tm_seed] = '-'
                colcls[tm_seed] = ''
        else:
            for rnd, cur_pts in team_pts[tm_seed].items():
                pts_for[tm_seed][rnd] = fmt_score(cur_pts)
            for rnd, cur_pts in opp_pts[tm_seed].items():
                pts_against[tm_seed][rnd] = fmt_score(cur_pts)

    updated = now_str()
    if tot_pts > prev_tot_pts:
        session[RR_DASH_KEY] = {
            'updated'    : updated,
            'done'       : done,
            'tot_gms'    : tot_gms,
            'tot_pts'    : tot_pts,
            'wins'       : wins,
            'losses'     : losses,
            'team_pts'   : team_pts,
            'opp_pts'    : opp_pts,
            'pts_for'    : pts_for,
            'pts_against': pts_against,
            'stats'      : stats,
            'mvmt'       : mvmt,
            'colcls'     : colcls
        }

    context = {
        'dash_num'    : 1,
        'title'       : RR_DASH,
        'updated'     : updated,
        'update_int'  : update_int,
        'done'        : done,
        'tourn'       : tourn,
        'rnds'        : tourn.tourn_rounds,
        'div_list'    : div_list,
        'div_teams'   : div_teams,
        'win_tallies' : win_tallies,
        'loss_tallies': loss_tallies,
        'pts_for'     : pts_for,
        'pts_against' : pts_against,
        'stats'       : stats,
        'mvmt'        : mvmt,
        'colcls'      : colcls
    }
    return render_dash(context)

################
# POST actions #
################

def create_tourn(form: dict) -> str:
    """
    """
    err_msg   = None
    tourn     = None
    new_tourn = False
    roster_fn = None
    view      = None

    tourn_name  = form.get('tourn_name')
    timeframe   = form.get('timeframe') or None
    venue       = form.get('venue') or None
    overwrite   = form.get('overwrite')
    roster_file = request.files.get('roster_file')
    if roster_file:
        roster_fn = secure_filename(roster_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_fn)
        roster_file.save(roster_path)

    try:
        db_init(tourn_name)
        tourn = tourn_create(timeframe=timeframe, venue=venue, force=bool(overwrite))
        if roster_file:
            upload_roster(roster_path)
            view = View.PLAYERS
            tourn = TournInfo.get()
        else:
            # TEMP: prompt for uploaded in the UI!!!
            err_msg = "Roster file required (manual roster creation not yet supported)"
    except OperationalError as e:
        if re.fullmatch(r'table "(\w+)" already exists', str(e)):
            err_msg = f"Tournament \"{tourn_name}\" already exists; either check \"Overwrite Existing\" or specify a new name"
        else:
            err_msg = cap_first(str(e))
        tourn = TournInfo(name=tourn_name, timeframe=timeframe, venue=venue)
        new_tourn = True

    context = {
        'tourn'      : tourn,
        'new_tourn'  : new_tourn,
        'overwrite'  : overwrite,
        'roster_file': roster_fn,
        'err_msg'    : err_msg,
        'view'       : view
    }
    return render_app(context)

def update_tourn(form: dict) -> str:
    """
    """
    err_msg   = None
    tourn     = None
    new_tourn = False
    roster_fn = None
    view      = None

    tourn_name  = form.get('tourn_name')
    timeframe   = form.get('timeframe') or None
    venue       = form.get('venue') or None
    roster_file = request.files.get('roster_file')
    if roster_file:
        roster_fn = secure_filename(roster_file.filename)
        roster_path = os.path.join(UPLOAD_DIR, roster_fn)
        roster_file.save(roster_path)

    try:
        db_init(tourn_name)
        tourn = TournInfo.get(True)
        tourn.timeframe = timeframe
        tourn.venue = venue
        tourn.save()
        if roster_file:
            upload_roster(roster_path)
            view = View.PLAYERS
            tourn = TournInfo.get()
        else:
            # TEMP: prompt for uploaded in the UI!!!
            err_msg = "Roster file required (manual roster creation not yet supported)"
    except OperationalError as e:
        err_msg = cap_first(str(e))
        tourn = TournInfo(name=tourn_name, timeframe=timeframe, venue=venue)
        new_tourn = True

    context = {
        'tourn'      : tourn,
        'new_tourn'  : new_tourn,
        'roster_file': roster_fn,
        'err_msg'    : err_msg,
        'view'       : view
    }
    return render_app(context)

def gen_player_nums(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    generate_player_nums()
    view = View.PLAYERS

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def gen_seed_bracket(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    build_seed_bracket()
    view = View.SEEDING

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def fake_seed_results(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    fake_seed_games()
    view = View.SEEDING

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def tabulate_seed_results(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    validate_seed_round(finalize=True)
    compute_player_seeds()
    prepick_champ_partners()
    view = View.PARTNERS

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def fake_partner_picks(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    fake_pick_partners()
    view = View.PARTNERS

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def comp_team_seeds(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    build_tourn_teams()
    compute_team_seeds()
    view = View.TEAMS

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def gen_tourn_brackets(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    build_tourn_bracket()
    view = View.ROUND_ROBIN

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def fake_tourn_results(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    fake_tourn_games()
    view = View.ROUND_ROBIN

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

def tabulate_tourn_results(form: dict) -> str:
    """
    """
    view        = None

    tourn_name  = form.get('tourn_name')
    db_init(tourn_name)
    validate_tourn(finalize=True)
    compute_team_ranks(finalize=True)
    view = View.TEAMS

    context = {
        'tourn'      : TournInfo.get(),
        'view'       : view
    }
    return render_app(context)

#############
# Renderers #
#############

SEL_SEP = "----------------"
SEL_NEW = "(create new)"
BUTTONS = SUBMIT_FUNCS

# button index to tuple of stages for which button is enabled
BUTTON_MAP = {
    2:  (TournStage.PLAYER_ROSTER, TournStage.PLAYER_NUMS),
    3:  (TournStage.PLAYER_NUMS,),
    4:  (TournStage.SEED_BRACKET, TournStage.SEED_RESULTS),
    5:  (TournStage.SEED_RESULTS,),
    6:  (TournStage.SEED_RANKS,),
    7:  (TournStage.PARTNER_PICK,),
    8:  (TournStage.TEAM_SEEDS,),
    9:  (TournStage.TOURN_BRACKET, TournStage.TOURN_RESULTS),
    10: (TournStage.TOURN_RESULTS,)
}

def render_app(context: dict) -> str:
    """Common post-processing of context before rendering the main app page through Jinja
    """
    view_name = None
    view_chk = [''] * len(View)
    view = context.get('view')
    if isinstance(view, int):
        view_name = VIEW_NAME[view]
        view_chk[view] = CHECKED

    stage_compl = 0
    if context.get('tourn'):
        stage_compl = context['tourn'].stage_compl or 0
    btn_attr = [''] * len(BUTTONS)
    for btn_idx, btn_stages in BUTTON_MAP.items():
        if stage_compl not in btn_stages:
            btn_attr[btn_idx] += DISABLED

    base_ctx = {
        'title'    : APP_NAME,
        'tourn_sel': get_tourns() + [SEL_SEP, SEL_NEW],
        'sel_sep'  : SEL_SEP,
        'sel_new'  : SEL_NEW,
        'view_name': view_name,
        'view_chk' : view_chk,
        'err_msg'  : None,       # context may contain override
        'pl_layout': pl_layout,
        'sg_layout': sg_layout,
        'pt_layout': pt_layout,
        'tm_layout': tm_layout,
        'tg_layout': tg_layout,
        'btn_val'  : BUTTONS,
        'btn_attr' : btn_attr,
        'help_txt' : help_txt
    }
    return render_template(APP_TEMPLATE, **(base_ctx | context))

def render_chart(context: dict) -> str:
    """Common post-processing of context before rendering chart pages through Jinja
    """
    return render_template(CHART_TEMPLATE, **context)

def render_dash(context: dict) -> str:
    """Common post-processing of context before rendering live dashboard pages through
    Jinja
    """
    return render_template(DASH_TEMPLATE, **context)

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
    through to the front-end, with the format being context-depedent (e.g. dict or list
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

#########################
# Content / Metacontent #
#########################

help_txt = {
    # tag: help text
}

############
# __main__ #
############

if __name__ == "__main__":
    app.run(debug=True, port=5050)
