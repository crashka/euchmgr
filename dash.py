#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Blueprint for live dashboard rendering
"""

from flask import Blueprint, session, render_template, abort

from database import now_str, db_init
from schema import GAME_PTS, TournInfo, Player, PlayerGame, Team, TeamGame
from chart import Numeric, round_val, fmt_tally

#################
# utility stuff #
#################

DashStat = Numeric | str
UNDEF = '-- undef --'

def fmt_dash_score(pts: int, prev_pts: int = -1) -> str:
    """Version for live dashboards--markup score if changed from prev (em); do not
    highlight game-winner scores (too distracting)
    """
    # special case for byes (no markup)
    if pts == -1:
        return '-'

    ret = str(pts)
    #if pts >= GAME_PTS:
    #    ret = f"<i>{ret}</i>"

    if prev_pts != -1 and pts != prev_pts:
        assert pts >= (prev_pts or 0)
        ret = f"<b>{ret}</b>"

    return ret

def fmt_dash_stat(val: DashStat, prev_val: DashStat = UNDEF, no_style: bool = False) -> str:
    """Version for live dashboards--markup stat if changed from prev (em), do rounding for
    float values.  Note that float vals are assumed to represent percentages (percent sign
    to be style along with the val itself).
    """
    if val is None:
        return ''

    if prev_val == UNDEF or no_style:
        # no previous reference is treated as no change, no styling
        if isinstance(val, float):
            return f"{round_val(val)}%"
        elif isinstance(val, int):
            return str(val)
        assert isinstance(val, str)
        return val
    elif prev_val is None:
        # previously empty represents changed value
        if isinstance(val, float):
            return f"<b>{round_val(val)}%</b>"
        return f"<b>{val}</b>"

    if isinstance(val, float):
        assert isinstance(prev_val, float)
        if round_val(val) == round_val(prev_val):
            return f"{round_val(val)}%"
        return f"<b>{round_val(val)}%</b>"
    elif isinstance(val, int):
        assert isinstance(prev_val, int)
        if val == prev_val:
            return str(val)
        return f"<b>{val}</b>"
    assert isinstance(val, str)
    assert isinstance(prev_val, str)
    if val == prev_val:
        return val
    return f"<b>{val}</b>"

###################
# blueprint stuff #
###################

dash = Blueprint('dash', __name__)
DASH_TEMPLATE = "dash.html"

SD_DASH = "Seeding Round Live Dashboard"
RR_DASH = "Round Robin Live Dashboard"

DASH_FUNCS = [
    'sd_dash',
    'rr_dash'
]

# update intervals specified in msecs
BASE_UPDATE_INT = 5000
# adjustments are related to time spent processing
SD_UPDATE_ADJ = 350
RR_UPDATE_ADJ = 200

# CSS class to use for up and down movement
COLCLS_UP   = 'grn_fg'
COLCLS_DOWN = 'red_fg'

# session storage key
SD_DASH_KEY = 'sd_dash'
RR_DASH_KEY = 'rr_dash'

@dash.get("/<dash>")
def get_dash(dash: str) -> str:
    """Render specified live dashboard
    """
    if dash not in DASH_FUNCS:
        abort(404, f"Invalid dash '{dash}'")

    tourn_name = session.get('tourn')
    db_init(tourn_name)
    tourn = TournInfo.get(requery=True)
    return globals()[dash](tourn)

def render_dash(context: dict) -> str:
    """Common post-processing of context before rendering live dashboard pages through
    Jinja
    """
    return render_template(DASH_TEMPLATE, **context)

###########
# sd_dash #
###########

def sd_dash(tourn: TournInfo) -> str:
    """Render seed round live dashboard
    """
    update_int = BASE_UPDATE_INT - SD_UPDATE_ADJ
    done = tourn.seeding_done()

    sort_key = lambda pl: pl.player_rank_final or tourn.players
    pl_list  = sorted(Player.iter_players(), key=sort_key)
    # inner dict represents points by round {rnd: pts}
    team_pts = {pl.player_num: {} for pl in pl_list}
    opp_pts  = {pl.player_num: {} for pl in pl_list}
    wins     = {pl.player_num: 0 for pl in pl_list}
    losses   = {pl.player_num: 0 for pl in pl_list}
    tot_gms  = 0
    tot_pts  = 0

    pg_list = list(PlayerGame.iter_games(include_byes=True))
    not_bye = lambda g: not g.is_bye
    max_rnd = lambda ls: max(g.round_num for g in ls) if ls else 0
    cur_rnd = max_rnd(list(filter(not_bye, pg_list)))
    for pg in pg_list:
        pl_num = pg.player_num
        assert pl_num == pg.player.player_num
        rnd = pg.round_num
        assert rnd not in team_pts[pl_num]
        assert rnd not in opp_pts[pl_num]
        if not pg.is_bye:
            tot_gms += 1
            tot_pts += pg.team_pts
            team_pts[pl_num][rnd] = pg.team_pts
            opp_pts[pl_num][rnd] = pg.opp_pts
            if pg.is_winner:
                wins[pl_num] += 1
            else:
                losses[pl_num] += 1
        elif rnd <= cur_rnd:
            team_pts[pl_num][rnd] = -1
            opp_pts[pl_num][rnd] = -1

    prev_tot_gms     = 0
    prev_tot_pts     = 0
    prev_team_pts    = {}
    prev_opp_pts     = {}
    prev_pts_for     = {}
    prev_pts_against = {}
    prev_stats       = None
    prev_stats_fmt   = None
    prev_mvmt        = None
    prev_colcls      = None
    if prev_frame := session.get(SD_DASH_KEY):
        if str(tourn.created_at) > prev_frame['updated']:
            session.pop(SD_DASH_KEY)
        else:
            prev_tot_gms     = prev_frame['tot_gms']
            prev_tot_pts     = prev_frame['tot_pts']
            prev_team_pts    = prev_frame['team_pts']
            prev_opp_pts     = prev_frame['opp_pts']
            prev_pts_for     = prev_frame['pts_for']
            prev_pts_against = prev_frame['pts_against']
            prev_stats       = prev_frame['stats']
            prev_stats_fmt   = prev_frame['stats_fmt']
            prev_mvmt        = prev_frame['mvmt']
            prev_colcls      = prev_frame['colcls']

    # the following are all keyed off of player_num
    win_tallies  = {}
    loss_tallies = {}
    stats        = {}  # value: (win_pct, pts_pct, rank)
    stats_fmt    = {}  # value: (win_pct, pts_pct, rank)
    mvmt         = {}
    colcls       = {}
    # inner dict represents points (formatted!) by round
    pts_for      = {pl.player_num: {} for pl in pl_list}
    pts_against  = {pl.player_num: {} for pl in pl_list}
    for pl in pl_list:
        pl_num = pl.player_num

        # we always (re-)format win/loss tallies (for now)
        win_tallies[pl_num] = fmt_tally(wins[pl_num])
        loss_tallies[pl_num] = fmt_tally(losses[pl_num])

        # conditionally, we either format or reuse string values for pts_for/_agnst,
        # stats, mvmt, and colcls (always recompute if not done)
        if prev_stats:
            if tot_pts == prev_tot_pts and not done:
                pts_for[pl_num] = prev_pts_for[pl_num]
                pts_against[pl_num] = prev_pts_against[pl_num]
                stats_fmt[pl_num] = prev_stats_fmt[pl_num]
            else:
                for rnd, cur_pts in team_pts[pl_num].items():
                    prev_pts = prev_team_pts[pl_num].get(rnd)
                    pts_for[pl_num][rnd] = fmt_dash_score(cur_pts, prev_pts)
                for rnd, cur_pts in opp_pts[pl_num].items():
                    prev_pts = prev_opp_pts[pl_num].get(rnd)
                    pts_against[pl_num][rnd] = fmt_dash_score(cur_pts, prev_pts)

                stats[pl_num] = (
                    pl.seed_win_pct,
                    pl.player_pos_str,
                    pl.seed_pts_pct,
                    pl.tb_win_rec,
                    pl.tb_pts_rec,
                    pl.player_rank_final
                )
                stats_fmt[pl_num] = (
                    fmt_dash_stat(stats[pl_num][0], prev_stats[pl_num][0], no_style=True),
                    fmt_dash_stat(stats[pl_num][1], prev_stats[pl_num][1], no_style=True),
                    fmt_dash_stat(stats[pl_num][2], prev_stats[pl_num][2], no_style=True),
                    fmt_dash_stat(stats[pl_num][3], prev_stats[pl_num][3], no_style=True),
                    fmt_dash_stat(stats[pl_num][4], prev_stats[pl_num][4], no_style=True),
                    fmt_dash_stat(stats[pl_num][5], prev_stats[pl_num][5])
                )

            if tot_pts == prev_tot_pts and prev_mvmt:
                mvmt[pl_num] = prev_mvmt.get(pl_num, '')
                colcls[pl_num] = prev_colcls.get(pl_num, '')
            elif prev_stats[pl_num][5]:
                rank_diff = (prev_stats[pl_num][5] or 0) - (pl.player_rank_final or 0)
                if rank_diff > 0:
                    mvmt[pl_num] = f'+{rank_diff}'
                    colcls[pl_num] = COLCLS_UP
                elif rank_diff < 0:
                    mvmt[pl_num] = str(rank_diff)
                    colcls[pl_num] = COLCLS_DOWN
            if pl_num not in mvmt:
                mvmt[pl_num] = '-'
                colcls[pl_num] = ''
        else:
            for rnd, cur_pts in team_pts[pl_num].items():
                pts_for[pl_num][rnd] = fmt_dash_score(cur_pts)
            for rnd, cur_pts in opp_pts[pl_num].items():
                pts_against[pl_num][rnd] = fmt_dash_score(cur_pts)

            stats[pl_num] = (
                pl.seed_win_pct,
                pl.player_pos_str,
                pl.seed_pts_pct,
                pl.tb_win_rec,
                pl.tb_pts_rec,
                pl.player_rank_final
            )
            stats_fmt[pl_num] = (
                fmt_dash_stat(stats[pl_num][0], no_style=True),
                fmt_dash_stat(stats[pl_num][1], no_style=True),
                fmt_dash_stat(stats[pl_num][2], no_style=True),
                fmt_dash_stat(stats[pl_num][3], no_style=True),
                fmt_dash_stat(stats[pl_num][4], no_style=True),
                fmt_dash_stat(stats[pl_num][5])
            )

    updated = now_str()
    if tot_pts > prev_tot_pts:
        session[SD_DASH_KEY] = {
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
            'stats_fmt'  : stats_fmt,
            'mvmt'       : mvmt,
            'colcls'     : colcls
        }

    context = {
        'dash_num'    : 0,
        'title'       : SD_DASH,
        'updated'     : updated,
        'update_int'  : update_int,
        'done'        : done,
        'tourn'       : tourn,
        'rnds'        : tourn.seed_rounds,
        'players'     : pl_list,
        'win_tallies' : win_tallies,
        'loss_tallies': loss_tallies,
        'pts_for'     : pts_for,
        'pts_against' : pts_against,
        'stats_fmt'   : stats_fmt,
        'mvmt'        : mvmt,
        'colcls'      : colcls
    }
    return render_dash(context)

###########
# rr_dash #
###########

def rr_dash(tourn: TournInfo) -> str:
    """Render round robin live dashboard
    """
    update_int = BASE_UPDATE_INT - RR_UPDATE_ADJ
    done = tourn.round_robin_done()

    div_list = list(range(1, tourn.divisions + 1))
    sort_key = lambda tm: tm.div_rank_final or tourn.teams
    tm_list  = sorted(Team.iter_teams(), key=sort_key)
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
    prev_stats_fmt   = None
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
            prev_stats_fmt   = prev_frame['stats_fmt']
            prev_mvmt        = prev_frame['mvmt']
            prev_colcls      = prev_frame['colcls']

    div_teams    = {div: [] for div in div_list}
    # the following are all keyed off of team_seed
    win_tallies  = {}
    loss_tallies = {}
    stats        = {}  # value: (win_pct, pts_pct, rank)
    stats_fmt    = {}  # value: (win_pct, pts_pct, rank)
    mvmt         = {}
    colcls       = {}
    # inner dict represents points (formatted!) by round
    pts_for      = {tm.team_seed: {} for tm in tm_list}
    pts_against  = {tm.team_seed: {} for tm in tm_list}
    for tm in tm_list:
        div = tm.div_num
        tm_seed = tm.team_seed
        div_teams[div].append(tm)

        # we always (re-)format win/loss tallies (for now)
        win_tallies[tm_seed] = fmt_tally(wins[tm_seed])
        loss_tallies[tm_seed] = fmt_tally(losses[tm_seed])

        # conditionally, we either format or reuse string values for pts_for/_agnst,
        # stats, mvmt, and colcls (always recompute if done)
        if prev_stats:
            if tot_pts == prev_tot_pts and not done:
                pts_for[tm_seed] = prev_pts_for[tm_seed]
                pts_against[tm_seed] = prev_pts_against[tm_seed]
                stats_fmt[tm_seed] = prev_stats_fmt[tm_seed]
            else:
                for rnd, cur_pts in team_pts[tm_seed].items():
                    prev_pts = prev_team_pts[tm_seed].get(rnd)
                    pts_for[tm_seed][rnd] = fmt_dash_score(cur_pts, prev_pts)
                for rnd, cur_pts in opp_pts[tm_seed].items():
                    prev_pts = prev_opp_pts[tm_seed].get(rnd)
                    pts_against[tm_seed][rnd] = fmt_dash_score(cur_pts, prev_pts)

                stats[tm_seed] = (
                    tm.tourn_win_pct,
                    tm.div_pos_str,
                    tm.tourn_pts_pct,
                    tm.tb_win_rec,
                    tm.tb_pts_rec,
                    tm.div_rank_final
                )
                stats_fmt[tm_seed] = (
                    fmt_dash_stat(stats[tm_seed][0], prev_stats[tm_seed][0], no_style=True),
                    fmt_dash_stat(stats[tm_seed][1], prev_stats[tm_seed][1], no_style=True),
                    fmt_dash_stat(stats[tm_seed][2], prev_stats[tm_seed][2], no_style=True),
                    fmt_dash_stat(stats[tm_seed][3], prev_stats[tm_seed][3], no_style=True),
                    fmt_dash_stat(stats[tm_seed][4], prev_stats[tm_seed][4], no_style=True),
                    fmt_dash_stat(stats[tm_seed][5], prev_stats[tm_seed][5])
                )

            if tot_pts == prev_tot_pts and prev_mvmt:
                mvmt[tm_seed] = prev_mvmt.get(tm_seed, '')
                colcls[tm_seed] = prev_colcls.get(tm_seed, '')
            elif prev_stats[tm_seed][5]:
                rank_diff = (prev_stats[tm_seed][5] or 0) - (tm.div_rank_final or 0)
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
                pts_for[tm_seed][rnd] = fmt_dash_score(cur_pts)
            for rnd, cur_pts in opp_pts[tm_seed].items():
                pts_against[tm_seed][rnd] = fmt_dash_score(cur_pts)

            stats[tm_seed] = (
                tm.tourn_win_pct,
                tm.div_pos_str,
                tm.tourn_pts_pct,
                tm.tb_win_rec,
                tm.tb_pts_rec,
                tm.div_rank_final
            )
            stats_fmt[tm_seed] = (
                fmt_dash_stat(stats[tm_seed][0], no_style=True),
                fmt_dash_stat(stats[tm_seed][1], no_style=True),
                fmt_dash_stat(stats[tm_seed][2], no_style=True),
                fmt_dash_stat(stats[tm_seed][3], no_style=True),
                fmt_dash_stat(stats[tm_seed][4], no_style=True),
                fmt_dash_stat(stats[tm_seed][5])
            )

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
            'stats_fmt'  : stats_fmt,
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
        'stats_fmt'   : stats_fmt,
        'mvmt'        : mvmt,
        'colcls'      : colcls
    }
    return render_dash(context)
