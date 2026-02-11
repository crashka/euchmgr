# -*- coding: utf-8 -*-

"""Blueprint for live dashboard rendering
"""

from itertools import groupby

from flask import Blueprint, session, render_template, abort

from schema_base import now_str
from schema import (fmt_pct, GAME_PTS, TournInfo, Player, PlayerGame, Team, TeamGame,
                    PartnerPick, PlayoffGame)
from chart import Numeric, fmt_tally

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
        return '&ndash;'

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
            return f"{fmt_pct(val)}"
        elif isinstance(val, int):
            return str(val)
        assert isinstance(val, str)
        return val
    elif prev_val is None:
        # previously empty represents changed value
        if isinstance(val, float):
            return f"<b>{fmt_pct(val)}</b>"
        return f"<b>{val}</b>"

    if isinstance(val, float):
        assert isinstance(prev_val, float)
        if fmt_pct(val) == fmt_pct(prev_val):
            return f"{fmt_pct(val)}"
        return f"<b>{fmt_pct(val)}</b>"
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
BRACKET_TEMPLATE = "bracket.html"

SD_DASH = "Seeding Round Live Dashboard"
RR_DASH = "Round Robin Live Dashboard"
PT_DASH = "Partner Picks Live Dashboard"
FF_DASH = "Final Four Live Bracket"

DASH_FUNCS = [
    'sd_dash',
    'rr_dash',
    'pt_dash',
    'ff_dash'
]

# update intervals specified in msecs
DASH_UPDATE_INT = 5000
BRACKET_UPDATE_INT = 10000
# adjustments are related to time spent processing
SD_UPDATE_ADJ = 350
RR_UPDATE_ADJ = 200
PT_UPDATE_ADJ = 100
FF_UPDATE_ADJ = 100

# CSS class to use for up and down movement
COLCLS_UP   = 'grn_fg'
COLCLS_DOWN = 'red_fg'

# session storage key
SD_DASH_KEY = 'sd_dash'
RR_DASH_KEY = 'rr_dash'
PT_DASH_KEY = 'pt_dash'
FF_DASH_KEY = 'ff_dash'

@dash.get("/<dash>")
def get_dash(dash: str) -> str:
    """Render specified live dashboard
    """
    if dash not in DASH_FUNCS:
        abort(404, f"Invalid dash '{dash}'")

    tourn = TournInfo.get(requery=True)
    return globals()[dash](tourn)

def render_dash(context: dict) -> str:
    """Common post-processing of context before rendering live dashboard pages through
    Jinja
    """
    return render_template(DASH_TEMPLATE, **context)

def render_bracket(context: dict) -> str:
    """Common post-processing of context before rendering live dashboard pages through
    Jinja
    """
    return render_template(BRACKET_TEMPLATE, **context)

###########
# sd_dash #
###########

def sd_dash(tourn: TournInfo) -> str:
    """Render seed round live dashboard
    """
    update_int = DASH_UPDATE_INT - SD_UPDATE_ADJ
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
                    pl.player_rank_final
                )
                stats_fmt[pl_num] = (
                    fmt_dash_stat(stats[pl_num][0], prev_stats[pl_num][0], no_style=True),
                    fmt_dash_stat(stats[pl_num][1], prev_stats[pl_num][1], no_style=True),
                    fmt_dash_stat(stats[pl_num][2], prev_stats[pl_num][2], no_style=True),
                    fmt_dash_stat(stats[pl_num][3], prev_stats[pl_num][3])
                )

            if tot_pts == prev_tot_pts and prev_mvmt:
                mvmt[pl_num] = prev_mvmt.get(pl_num, '')
                colcls[pl_num] = prev_colcls.get(pl_num, '')
            elif prev_stats[pl_num][3]:
                rank_diff = (prev_stats[pl_num][3] or 0) - (pl.player_rank_final or 0)
                if rank_diff > 0:
                    mvmt[pl_num] = f'+{rank_diff}'
                    colcls[pl_num] = COLCLS_UP
                elif rank_diff < 0:
                    mvmt[pl_num] = str(rank_diff)
                    colcls[pl_num] = COLCLS_DOWN
            if pl_num not in mvmt:
                mvmt[pl_num] = '&ndash;'
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
                pl.player_rank_final
            )
            stats_fmt[pl_num] = (
                fmt_dash_stat(stats[pl_num][0], no_style=True),
                fmt_dash_stat(stats[pl_num][1], no_style=True),
                fmt_dash_stat(stats[pl_num][2], no_style=True),
                fmt_dash_stat(stats[pl_num][3])
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
    update_int = DASH_UPDATE_INT - RR_UPDATE_ADJ
    done = tourn.round_robin_done()

    div_list = list(range(1, tourn.divisions + 1))
    sort_key = lambda tm: tm.div_rank_final or tourn.teams
    tm_list  = sorted(Team.iter_teams(), key=sort_key)
    # inner dict represents points by round {rnd: pts}
    team_pts = {tm.id: {} for tm in tm_list}
    opp_pts  = {tm.id: {} for tm in tm_list}
    wins     = {tm.id: 0 for tm in tm_list}
    losses   = {tm.id: 0 for tm in tm_list}
    tot_gms  = 0
    tot_pts  = 0

    tg_list = list(TeamGame.iter_games(include_byes=True))
    not_bye = lambda g: not g.is_bye
    max_rnd = lambda ls: max(g.round_num for g in ls) if ls else 0
    cur_rnd = {div: max_rnd(list(filter(not_bye, tg_list))) for div in div_list}
    for tg in tg_list:
        div = tg.team.div_num
        tm_id = tg.team_id
        assert tm_id == tg.team.id
        rnd = tg.round_num
        assert rnd not in team_pts[tm_id]
        assert rnd not in opp_pts[tm_id]
        if not tg.is_bye:
            tot_gms += 1
            tot_pts += tg.team_pts
            team_pts[tm_id][rnd] = tg.team_pts
            opp_pts[tm_id][rnd] = tg.opp_pts
            if tg.is_winner:
                wins[tm_id] += 1
            else:
                losses[tm_id] += 1
        elif rnd <= cur_rnd[div]:
            team_pts[tm_id][rnd] = -1
            opp_pts[tm_id][rnd] = -1

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
    # the following are all keyed off of team id
    win_tallies  = {}
    loss_tallies = {}
    stats        = {}  # value: (win_pct, pts_pct, rank)
    stats_fmt    = {}  # value: (win_pct, pts_pct, rank)
    mvmt         = {}
    colcls       = {}
    # inner dict represents points (formatted!) by round
    pts_for      = {tm.id: {} for tm in tm_list}
    pts_against  = {tm.id: {} for tm in tm_list}
    for tm in tm_list:
        div = tm.div_num
        tm_id = tm.id
        div_teams[div].append(tm)

        # we always (re-)format win/loss tallies (for now)
        win_tallies[tm_id] = fmt_tally(wins[tm_id])
        loss_tallies[tm_id] = fmt_tally(losses[tm_id])

        # conditionally, we either format or reuse string values for pts_for/_agnst,
        # stats, mvmt, and colcls (always recompute if done)
        if prev_stats:
            if tot_pts == prev_tot_pts and not done:
                pts_for[tm_id] = prev_pts_for[tm_id]
                pts_against[tm_id] = prev_pts_against[tm_id]
                stats_fmt[tm_id] = prev_stats_fmt[tm_id]
            else:
                for rnd, cur_pts in team_pts[tm_id].items():
                    prev_pts = prev_team_pts[tm_id].get(rnd)
                    pts_for[tm_id][rnd] = fmt_dash_score(cur_pts, prev_pts)
                for rnd, cur_pts in opp_pts[tm_id].items():
                    prev_pts = prev_opp_pts[tm_id].get(rnd)
                    pts_against[tm_id][rnd] = fmt_dash_score(cur_pts, prev_pts)

                stats[tm_id] = (
                    tm.tourn_win_pct,
                    tm.div_pos_str,
                    tm.tourn_pts_pct,
                    tm.div_tb_win_rec,
                    tm.div_tb_pts_pct,
                    tm.div_rank_final
                )
                stats_fmt[tm_id] = (
                    fmt_dash_stat(stats[tm_id][0], prev_stats[tm_id][0], no_style=True),
                    fmt_dash_stat(stats[tm_id][1], prev_stats[tm_id][1], no_style=True),
                    fmt_dash_stat(stats[tm_id][2], prev_stats[tm_id][2], no_style=True),
                    fmt_dash_stat(stats[tm_id][3], prev_stats[tm_id][3], no_style=True),
                    fmt_dash_stat(stats[tm_id][4], prev_stats[tm_id][4], no_style=True),
                    fmt_dash_stat(stats[tm_id][5], prev_stats[tm_id][5])
                )

            if tot_pts == prev_tot_pts and prev_mvmt:
                mvmt[tm_id] = prev_mvmt.get(tm_id, '')
                colcls[tm_id] = prev_colcls.get(tm_id, '')
            elif prev_stats[tm_id][5]:
                rank_diff = (prev_stats[tm_id][5] or 0) - (tm.div_rank_final or 0)
                if rank_diff > 0:
                    mvmt[tm_id] = f'+{rank_diff}'
                    colcls[tm_id] = COLCLS_UP
                elif rank_diff < 0:
                    mvmt[tm_id] = str(rank_diff)
                    colcls[tm_id] = COLCLS_DOWN
            if tm_id not in mvmt:
                mvmt[tm_id] = '&ndash;'
                colcls[tm_id] = ''
        else:
            for rnd, cur_pts in team_pts[tm_id].items():
                pts_for[tm_id][rnd] = fmt_dash_score(cur_pts)
            for rnd, cur_pts in opp_pts[tm_id].items():
                pts_against[tm_id][rnd] = fmt_dash_score(cur_pts)

            stats[tm_id] = (
                tm.tourn_win_pct,
                tm.div_pos_str,
                tm.tourn_pts_pct,
                tm.div_tb_win_rec,
                tm.div_tb_pts_pct,
                tm.div_rank_final
            )
            stats_fmt[tm_id] = (
                fmt_dash_stat(stats[tm_id][0], no_style=True),
                fmt_dash_stat(stats[tm_id][1], no_style=True),
                fmt_dash_stat(stats[tm_id][2], no_style=True),
                fmt_dash_stat(stats[tm_id][3], no_style=True),
                fmt_dash_stat(stats[tm_id][4], no_style=True),
                fmt_dash_stat(stats[tm_id][5])
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

###########
# pt_dash #
###########

def pt_dash(tourn: TournInfo) -> str:
    """Render seed round live dashboard
    """
    update_int = DASH_UPDATE_INT - PT_UPDATE_ADJ
    done = tourn.partner_picks_done()

    picks_made  = PartnerPick.get_picks() or []
    picks_avail = PartnerPick.avail_picks() or []
    cur_pick    = PartnerPick.current_pick()
    num_picks   = len(picks_made)
    num_avail   = len(picks_avail)
    prev_count  = 0

    if prev_frame := session.get(PT_DASH_KEY):
        if str(tourn.created_at) > prev_frame['updated']:
            session.pop(PT_DASH_KEY)
        else:
            prev_count = prev_frame['num_picks']

    updated = now_str()
    if num_picks > prev_count:
        session[PT_DASH_KEY] = {
            'updated'  : updated,
            'done'     : done,
            'num_picks': num_picks
        }

    context = {
        'dash_num'    : 2,
        'title'       : PT_DASH,
        'updated'     : updated,
        'update_int'  : update_int,
        'done'        : done,
        'tourn'       : tourn,
        'picks_made'  : picks_made,
        'picks_avail' : picks_avail,
        'cur_pick'    : cur_pick,
        'prev_count'  : prev_count
    }
    return render_dash(context)

###########
# ff_dash #
###########

def fmt_scores(games: list[PlayoffGame]) -> str:
    """Format matchup game scores for display.
    """
    scores = []
    for i, gm in enumerate(games):
        if not gm.winner:
            continue
        scores.append(f"Game {i + 1}:&nbsp;&nbsp;{gm.team1_pts} - {gm.team2_pts}")
    return "<br>".join(scores)

def ff_dash(tourn: TournInfo) -> str:
    """Render final four live bracket
    """
    update_int = BRACKET_UPDATE_INT - FF_UPDATE_ADJ
    done = tourn.playoffs_done()

    # match_ident: (team1, team2, winner, [games])
    brckt_info = {}
    ncomplete = 0
    prev_count  = 0

    by_matchup = PlayoffGame.iter_games(by_matchup=True)
    for k, g in groupby(by_matchup, key=lambda x: x.matchup_ident):
        matchup = k
        games = list(g)
        team1 = games[0].team1
        team2 = games[0].team2
        winner = games[0].matchup_winner
        brckt_info[matchup] = (team1, team2, winner, games)
        ncomplete += sum(1 for x in games if x.winner)

    if prev_frame := session.get(FF_DASH_KEY):
        if str(tourn.created_at) > prev_frame['updated']:
            session.pop(FF_DASH_KEY)
        else:
            prev_count = prev_frame['ncomplete']

    updated = now_str()
    if ncomplete > prev_count:
        session[FF_DASH_KEY] = {
            'updated'  : updated,
            'done'     : done,
            'ncomplete': ncomplete
        }

    context = {
        'dash_num'  : 3,
        'title'     : FF_DASH,
        'updated'   : updated,
        'update_int': update_int,
        'done'      : done,
        'tourn'     : tourn,
        'brckt'     : brckt_info,
        'fmt_scores': fmt_scores
    }
    return render_bracket(context)
