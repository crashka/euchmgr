# -*- coding: utf-8 -*-

from typing import Self, Iterator

from peewee import ForeignKeyField, DeferredForeignKey, fn

from database import BaseModel
from schema import (rnd_pct, Bracket, BRACKET_NAME, TournStage, TournInfo, Player as BasePlayer,
                    SeedGame as BaseSeedGame, Team as BaseTeam, TournGame as BaseTournGame,
                    PlayoffGame as BasePlayoffGame, PlayerGame as BasePlayerGame,
                    TeamGame as BaseTeamGame, PostScore as BasePostScore)

#################
# utility stuff #
#################

# NOTE: more utility stuff at the bottom of this file

# used for various `fmt_stat` functions
Numeric = int | float

# special (i.e. hack) value representing n/a for percentages (must be a float)
PTS_PCT_NA = -1.0

PCT_PREC = 3
PCT_FMT = '.03f'

def fmt_pct(val: float) -> str:
    """Provide consistent formatting for percentage values (appropriate rounding and
    look), used for grids, charts, dashboards, and reports.
    """
    if val is None:
        return ''
    elif val == PTS_PCT_NA:
        return '&ndash;'  # or "n/a"?
    # take care of (possible!) exceptions first--yes, the code below may produce the same
    # string, but we want to allow ourselves the freedom to make this something different
    if val == 1.0:
        return '1.000'

    # make everything else look like .xxx (with trailing zeros)
    as_str = f"{round(val, PCT_PREC):{PCT_FMT}}"
    if as_str.startswith('0.'):
        return as_str[1:]
    # not expecting negative input or anything >1.0
    assert False, f"unexpected percentage value of '{val}'"

TALLY_FILE_PFX = "/static/tally_"
TALLY_FILE_SFX = ".png"
TALLY_HEIGHT = 15
TALLY_WIDTH = 50

def fmt_tally(pts: int) -> str:
    """Print arguments for <img> tag for showing point tallies
    """
    if pts == 0:
        return ''
    tally_file = f"{TALLY_FILE_PFX}{pts}{TALLY_FILE_SFX}"
    return f'src="{tally_file}" height="{TALLY_HEIGHT}" width="{TALLY_WIDTH}"'

###########
# UIMixin #
###########

class UIMixin:
    """Mixin to support compatibility with base schema instances.  NOTE: `ui` module
    classes must inherit from this mixin then the associated `schema` class.
    """
    def __hash__(self):
        """Use the hash of the base schema class (see NOTE in the docheader).
        """
        return hash((self.__class__.__mro__[2], self._pk))

    def __eq__(self, other):
        """Handle the case of comparing against a superclass instance.
        """
        return (
            (other.__class__ == self.__class__ or
             issubclass(self.__class__, other.__class__)) and
            self._pk is not None and
            self._pk == other._pk)

##########
# Player #
##########

EMPTY_PLYR_STATS = {
    'seed_wins'       : None,
    'seed_losses'     : None,
    'seed_pts_for'    : None,
    'seed_pts_against': None
}

class Player(UIMixin, BasePlayer):
    """Represents a player in the tournament, as well as a mobile (i.e. non-admin) user of
    the app.
    """
    partner   = ForeignKeyField('self', field='player_num', column_name='partner_num', null=True)
    partner2  = ForeignKeyField('self', field='player_num', column_name='partner2_num', null=True)
    picked_by = ForeignKeyField('self', field='player_num', column_name='picked_by_num', null=True)
    team      = DeferredForeignKey('Team', null=True)

    class Meta:
        table_name = BasePlayer._meta.table_name

    @classmethod
    def fetch_by_rank(cls, player_rank: int) -> Self:
        """Return player by player_rank (always retrieved from database), or `None` if not
        found
        """
        return cls.get_or_none(cls.player_rank == player_rank)

    @classmethod
    def fetch_by_name(cls, name: str) -> Self:
        """Return player by name (same as nick_name), or `None` if not found.  Always
        retrieved from database (not from local cache).
        """
        return cls.get_or_none(cls.nick_name == name)

    @classmethod
    def find_by_name_pfx(cls, name_pfx: str) -> Iterator[Self]:
        """Iterator returning players matching the specified (nick) name prefix
        """
        query = cls.select().where(cls.nick_name.startswith(name_pfx))
        for p in query.iterator():
            yield p

    @property
    def full_name(self) -> str:
        """For UI support (one field instead of two)
        """
        return self.first_name + ' ' + self.last_name

    @property
    def display_name(self) -> str:
        """For UI support (especially if/when sorting by last name)
        """
        friendly = self.name if self.name != self.last_name else self.first_name
        return f"{self.last_name} ({friendly})"

    @property
    def player_tag(self) -> str:
        """Combination of player_num and name with embedded HTML annotation (used for
        bracket and scores/results displays)
        """
        return f"<b>{self.player_num}</b>&nbsp;&nbsp;<u>{self.name}</u>"

    @property
    def player_data(self) -> dict:
        """Return player data as a dict, removing distracting default values if not relevant
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEED_BRACKET:
            return self.__data__ | EMPTY_PLYR_STATS
        return self.__data__

    @property
    def seed_ident(self) -> str:
        """Player "name (rank)", for partner picking UI
        """
        return f"{self.name} ({self.player_rank})"

    @property
    def picks_info(self) -> str | None:
        """For partner picking UI
        """
        pt_info = None
        if self.partner:
            pt_info = self.partner.seed_ident
            if self.partner2:
                pt_info += f", {self.partner2.seed_ident}"
        return pt_info

    @property
    def picks_info2(self) -> str | None:
        """For partner picking UI
        """
        pt_info = None
        if self.partner:
            pt_info = self.partner.seed_ident
            if self.partner2:
                pt_info += f"<br>{self.partner2.seed_ident}"
        return pt_info

    @property
    def picked_by_info(self) -> str | None:
        """For partner picking UI
        """
        return self.picked_by.seed_ident if self.picked_by else None

    @property
    def player_pos_str(self) -> str | None:
        """Same as player_pos, except annotated if tied with others
        """
        if self.player_pos is None:
            return None
        elif not self.seed_tb_crit:
            return str(self.player_pos)
        return f"{self.player_pos}*"

    @property
    def seed_win_pct_str(self) -> str:
        """Return seed_win_pct formatted as a string.
        """
        return fmt_pct(self.seed_win_pct)

    @property
    def seed_pts_pct_str(self) -> str:
        """Return seed_pts_pct formatted as a string.
        """
        return fmt_pct(self.seed_pts_pct)

    @property
    def player_rank_final(self, annotated: bool = False) -> int | str:
        """The official value for player ranking (defaults to player_rank, with override
        from player_rank_adj).  String value is returned if `annotated` is specified as
        True, with override indicated (if present).
        """
        if annotated:
            if self.player_rank_adj:
                return f"{self.player_rank_adj} ({self.player_rank})"
            else:
                return str(self.player_rank)

        return self.player_rank_adj or self.player_rank

    @property
    def current_game(self) -> BaseModel:
        """Return current SeedGame for player (only if seeding stage is active)
        """
        pg = (PlayerGame
              .select(fn.max(PlayerGame.round_num))
              .where(PlayerGame.player == self,
                     PlayerGame.is_bye == False)
              .get())
        last_round = pg.round_num or 0
        cg = (SeedGame
              .select()
              .where((SeedGame.player1 == self) |
                     (SeedGame.player2 == self) |
                     (SeedGame.player3 == self) |
                     (SeedGame.player4 == self))
              .where(SeedGame.table_num.is_null(False),
                     SeedGame.round_num > last_round)
              .order_by(SeedGame.round_num))
        return cg[0] if len(cg) > 0 else None

    def get_games(self, all_games: bool = False) -> list[BaseModel]:
        """Get completed SeedGame records (including possible byes up to the current round
        for the stage).
        """
        cur_round = SeedGame.current_round()
        if cur_round == 0:
            return None  # as distinct from [], e.g. game 1 in progress
        query = (SeedGame
                 .select()
                 .where((SeedGame.player1 == self) |
                        (SeedGame.player2 == self) |
                        (SeedGame.player3 == self) |
                        (SeedGame.player4 == self))
                 .order_by(SeedGame.round_num))
        if cur_round != -1 and not all_games:
            query = query.where(SeedGame.round_num <= cur_round)
        return list(query)

    def get_opps_games(self, opps: list[Self]) -> list[BaseModel]:
        """Get SeedGame records for all games versus specified opponents
        """
        query = (SeedGame
                 .select()
                 .join(PlayerGame, on=(PlayerGame.game_label == SeedGame.label))
                 .where(PlayerGame.player == self))
        # see NOTE in get_game_stats() (schema.py)
        opps_nums = [pl.player_num for pl in opps]
        query = query.where((PlayerGame.opponents.extract_text('0').in_(opps_nums)) |
                            (PlayerGame.opponents.extract_text('1').in_(opps_nums)))
        return list(query)

##################
# PlayerRegister #
##################

class PlayerRegister(UIMixin, BasePlayer):
    """Subclass of `Player` that represents the process of player registration process.
    Note that the cached player map is avoided in all calls, to avoid integrity problems.
    """
    class Meta:
        table_name = BasePlayer._meta.table_name

    @classmethod
    def phase_status(cls) -> str:
        """Return current status of the registration phase (for mobile UI).
        """
        tourn = TournInfo.get()
        nreg = len(list(cls.nums_used()))
        if nreg < tourn.players:
            return f"{nreg} players registered"
        else:
            return "Done"

    @classmethod
    def reg_status(cls, player: Player) -> str:
        """Have to do this as a class method, since we are not (currently) instantiating
        objects for this class.
        """
        return "Registered" if player.player_num else "Pending"

###############
# PartnerPick #
###############

class PartnerPick(UIMixin, BasePlayer):
    """Subclass of `Player` that represents the process of picking partners.  Note that
    the cached player map is avoided in all calls, to avoid integrity problems.
    """
    class Meta:
        table_name = BasePlayer._meta.table_name

    @classmethod
    def current_round(cls) -> int:
        """Return the current round for partner picking, with the special values of `0` to
        indicate that the seeding stage rankings have not yet been determined, and `-1` to
        indicate that the partner picking stage is complete.
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEED_RANKS:
            return 0

        query = (cls
                 .select(fn.count())
                 .where(cls.partner.is_null(False)))
        npicks = query.scalar()
        if npicks < tourn.teams:
            return npicks + 1
        return -1

    @classmethod
    def phase_status(cls) -> str:
        """Return current status of the partner picking phase (for mobile UI).
        """
        cur_round = cls.current_round()
        if cur_round == 0:
            return "Not Started"
        elif cur_round == -1:
            return "Done"
        else:
            if cur_round == 2:
                # ignore the reigning champ(s) pre-selected team
                npicks = "no"
            else:
                npicks = cur_round - 2
            return f"{npicks} picks made"

    @classmethod
    def current_pick(cls) -> Self:
        """Return top seeded player currently available, which equates to the player
        currently picking during the partner selection process.
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEED_RANKS:
            return None

        # NOTE: need to instantiate `Player` instances here
        pl_query = Player.select()
        avail = list(filter(lambda x: x.available, pl_query))
        if not avail:
            return None
        assert len(avail) > 1
        return sorted(avail, key=lambda x: x.player_rank)[0]

    @classmethod
    def avail_picks(cls) -> list[Self]:
        """Strangely (and rather unfortunately) similar to `Player.available_players`,
        except that we stay away from the cached player map here and exclude the current
        picker.  It would be nice to clean things up and eliminate some redundancy (also
        see `current_pick`) and sources of possible confusion (not to mention cache
        problems).
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEED_RANKS:
            return None  # as distinguished from `[]` (below)

        # NOTE: need to instantiate `Player` instances here (as above)
        pl_iter = Player.iter_players(by_rank=True)
        avail = list(filter(lambda x: x.available, pl_iter))
        if not avail:
            return []
        assert len(avail) > 1
        return avail[1:]

    @classmethod
    def get_picks(cls, all_picks: bool = False) -> list[BaseModel]:
        """Get completed "PartnerPick" records (corresponding to players that have made a
        pick), in order of pick position (i.e. seeding rank), with reigning champs always
        listed first.  `all_picks` indicates that players yet to pick (and not already
        picked themselves) should also be returned.

        This call follows the same semantics as `get_games` (for "BracketPick" objects).
        """
        cur_round = cls.current_round()
        if cur_round == 0:
            return None  # as distinct from [], e.g. pick 1 in progress

        # NOTE: need to instantiate `Player` instances here (as above)--also, don't muck
        # with the cached player map since we will always want to requery and this may be
        # called in (relative) volume; we keep this simple and just do the filtering in
        # code (should probably also do the same elsewhere!)
        pl_list = list(Player.select())
        if all_picks or cur_round == -1:
            includer = lambda x: not x.picked_by
        else:
            includer = lambda x: x.partner
        picks = filter(includer, pl_list)
        return sorted(picks, key=lambda x: (-x.reigning_champ, x.player_rank))

############
# SeedGame #
############

class SeedGame(UIMixin, BaseSeedGame):
    """Represents a player in the tournament, as well as a mobile (i.e. non-admin) user of
    the app.
    """
    player1 = ForeignKeyField(Player, field='player_num', column_name='player1_num')
    player2 = ForeignKeyField(Player, field='player_num', column_name='player2_num', null=True)
    player3 = ForeignKeyField(Player, field='player_num', column_name='player3_num', null=True)
    player4 = ForeignKeyField(Player, field='player_num', column_name='player4_num', null=True)

    class Meta:
        table_name = BaseSeedGame._meta.table_name

    @classmethod
    def current_round(cls) -> int:
        """Return the current round of play, with the special values of `0` to indicate
        that the seeding bracket has not yet been created, and `-1` to indicate that the
        seeding stage is complete.
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEED_BRACKET:
            return 0

        round_games = tourn.players // 4
        query = (cls
                 .select(cls.round_num, fn.count(cls.id))
                 .where(cls.winner.is_null(False))
                 .group_by(cls.round_num)
                 .order_by(cls.round_num.desc()))
        if not query:
            return 1  # no games yet played
        round_num, ngames = query.scalar(as_tuple=True)

        if ngames < round_games:
            return round_num
        if round_num < tourn.seed_rounds:
            return round_num + 1
        return -1

    @classmethod
    def phase_status(cls) -> str:
        """Return current status of the seeding round phase (for mobile UI).
        """
        cur_round = cls.current_round()
        if cur_round == 0:
            return "Not Started"
        elif cur_round == -1:
            return "Done"
        else:
            return f"Round {cur_round}"

    @property
    def bracket_ident(self) -> str:
        """Display name for the bracket
        """
        return BRACKET_NAME[Bracket.SEED]

    @property
    def player_nums(self) -> str:
        """Used for the seeding view of the UI
        """
        pl_nums = list(filter(bool, (self.player1_num,
                                     self.player2_num,
                                     self.player3_num,
                                     self.player4_num)))
        if len(pl_nums) < 4:
            return ', '.join(map(str, pl_nums))

        return f"{pl_nums[0]} / {pl_nums[1]} vs. {pl_nums[2]} / {pl_nums[3]}"

    @property
    def team_tags(self) -> tuple[str, str]:
        """Team references based on player tags with embedded HTML annotation (used for
        bracket and scores/results displays)--currently, can only be called for actual
        matchup, and not bye records
        """
        p1 = self.player1
        p2 = self.player2
        p3 = self.player3
        p4 = self.player4
        assert p1 and p2 and p3 and p4
        team1_tag = f"{p1.player_tag}&nbsp;&nbsp;/&nbsp;&nbsp;{p2.player_tag}"
        team2_tag = f"{p3.player_tag}&nbsp;&nbsp;/&nbsp;&nbsp;{p4.player_tag}"
        return team1_tag, team2_tag

    @property
    def bye_tags(self) -> list[str]:
        """Bye references based on player tags with embedded HTML annotation (used for
        bracket and scores/results displays)--currently, can only be called for bye
        records
        """
        pl_list = list(filter(bool, (self.player1,
                                     self.player2,
                                     self.player3,
                                     self.player4)))
        assert len(pl_list) < 4  # ...or return None?
        return [pl.player_tag for pl in pl_list]

    @property
    def winner_info(self) -> tuple[str, int, int]:
        """Returns tuple(team_name, team_pts)
        """
        if self.team1_name == self.winner:
            return self.team1_tag, self.team1_pts
        else:
            return self.team2_tag, self.team2_pts

    @property
    def loser_info(self) -> tuple[str, int, int]:
        """Returns tuple(team_name, team_pts)
        """
        if self.team1_name == self.winner:
            return self.team2_tag, self.team2_pts
        else:
            return self.team1_tag, self.team1_pts

    @property
    def team1_tag(self) -> str:
        """REVISIT: need to reconcile this with fmt_team_name (in euchmgr.py)!!!
        """
        pl_tag = lambda x: f"{x.name} ({x.player_num})"
        return f"{pl_tag(self.player1)} / {pl_tag(self.player2)}"

    @property
    def team2_tag(self) -> str:
        """REVISIT: need to reconcile this with fmt_team_name (in euchmgr.py)!!!
        """
        pl_tag = lambda x: f"{x.name} ({x.player_num})"
        return f"{pl_tag(self.player3)} / {pl_tag(self.player4)}"

    def team_idx(self, player: Player) -> int:
        """Return the team index for the specified player: `0`, `1`, or `-1`, representing
        team1, team2, or a bye (respectively).  This is used to map into `team_tags`.
        """
        if player in (self.player1, self.player2):
            return 0 if self.table_num else -1
        if player in (self.player3, self.player4):
            return 1 if self.table_num else -1
        raise LogicError(f"player '{player.name}' not in seed_game '{self.label}'")

    def team_info(self, player: Player) -> tuple[str, int, int]:
        """Returns tuple(team_name, team_pts)
        """
        if self.is_winner(player):
            return self.winner_info
        else:
            return self.loser_info

    def opp_info(self, player: Player) -> tuple[str, int, int]:
        """Returns tuple(team_name, team_pts)
        """
        if self.is_winner(player):
            return self.loser_info
        else:
            return self.winner_info

    def is_winner(self, player: Player) -> bool:
        """Cleaner interface for use in templates
        """
        pg = PlayerGame.get(PlayerGame.player == player,
                            PlayerGame.game_label == self.label)
        return pg.is_winner

########
# Team #
########

EMPTY_TEAM_STATS = {
    'tourn_wins'       : None,
    'tourn_losses'     : None,
    'tourn_pts_for'    : None,
    'tourn_pts_against': None
}

EMPTY_FINAL_FOUR_STATS = {
    'playoff_match_wins'  : None,
    'playoff_match_losses': None,
    'playoff_wins'        : None,
    'playoff_losses'      : None,
    'playoff_pts_for'     : None,
    'playoff_pts_against' : None
}

class Team(UIMixin, BaseTeam):
    """
    """
    player1 = ForeignKeyField(Player, field='player_num', column_name='player1_num')
    player2 = ForeignKeyField(Player, field='player_num', column_name='player2_num')
    player3 = ForeignKeyField(Player, field='player_num', column_name='player3_num', null=True)

    class Meta:
        table_name = BaseTeam._meta.table_name

    @property
    def team_data(self) -> dict:
        """Return team data as a dict, removing distracting default values if not relevant
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.TOURN_BRACKET:
            return self.__data__ | EMPTY_TEAM_STATS
        return self.__data__

    @property
    def final_four_data(self) -> dict:
        """Return final four team data as a dict, removing distracting default values if
        not relevant
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEMIS_BRACKET:
            return self.__data__ | EMPTY_FINAL_FOUR_STATS
        return self.__data__

    @property
    def player_nums(self) -> str:
        """Used for the teams view of the UI
        """
        pl_nums = list(filter(bool, (self.player1_num,
                                     self.player2_num,
                                     self.player3_num)))
        return ' / '.join(map(str, pl_nums))

    @property
    def tourn_win_pct_str(self) -> str:
        """Return tourn_win_pct formatted as a string.
        """
        return fmt_pct(self.tourn_win_pct)

    @property
    def tourn_pts_pct_str(self) -> str:
        """Return tourn_pts_pct formatted as a string.
        """
        return fmt_pct(self.tourn_pts_pct)

    @property
    def team_tag(self) -> str:
        """Combination of div_seed and team_name with embedded HTML annotation (used for
        bracket and scores/results displays)
        """
        return f"<b>{self.div_seed}</b>&nbsp;&nbsp;<u>{self.team_name}</u>"

    @property
    def team_tag_pl(self) -> str:
        """Same as `team_tag`, but for playoff bracket (so tourn_rank)
        """
        return f"<b>{self.tourn_rank}</b>&nbsp;&nbsp;{self.team_name}"

    @property
    def playoff_win_pct_str(self) -> str:
        """Return playoff_win_pct formatted as a string.
        """
        return fmt_pct(self.playoff_win_pct)

    @property
    def playoff_pts_pct_str(self) -> str:
        """Return playoff_pts_pct formatted as a string.
        """
        return fmt_pct(self.playoff_pts_pct)

    @property
    def playoff_match_rec(self) -> str | None:
        """Return playoff match record (W-L) as a string
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEMIS_BRACKET:
            return None
        return f"{self.playoff_match_wins}-{self.playoff_match_losses}"

    @property
    def playoff_win_rec(self) -> str | None:
        """Return playoff game win record (W-L) as a string
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEMIS_BRACKET:
            return None
        return f"{self.playoff_wins}-{self.playoff_losses}"

    @property
    def div_pos_str(self) -> str | None:
        """Same as div_pos, except annotated if tied with others
        """
        if self.div_pos is None:
            return None
        elif not self.div_tb_crit:
            return str(self.div_pos)
        return f"{self.div_pos}*"

    @property
    def div_tb_win_rec(self) -> str | None:
        """Tie-breaker (head-to-head) win-loss record as a string
        """
        if not self.div_tb_data:
            return None
        return f"{self.div_tb_data['wins']}-{self.div_tb_data['losses']}"

    @property
    def div_tb_pts_rec(self) -> str | None:
        """Tie-breaker (head-to-head) points for-and-against record as a string
        """
        if not self.div_tb_data:
            return None
        return f"{self.div_tb_data['pts_for']}-{self.div_tb_data['pts_against']}"

    @property
    def div_tb_pts_pct(self) -> float | None:
        """Tie-breaker (head-to-head) points percentage (points-for over total points)
        """
        if not self.div_tb_data:
            return None
        tb_pts_tot = self.div_tb_data['pts_for'] + self.div_tb_data['pts_against']
        if tb_pts_tot == 0.0:
            return PTS_PCT_NA
        return rnd_pct(self.div_tb_data['pts_for'] / tb_pts_tot)

    @property
    def div_rank_final(self, annotated: bool = False) -> int | str:
        """The official value for division ranking (defaults to div_rank, with override
        from div_rank_adj).  String value is returned if `annotated` is specified as True,
        with override indicated (if present).
        """
        if annotated:
            if self.div_rank_adj:
                return f"{self.div_rank_adj} ({self.div_rank})"
            else:
                return str(self.div_rank)

        return self.div_rank_adj or self.div_rank

    @property
    def current_game(self) -> BaseModel:
        """Return current TournGame for team (only if round robin stage is active)
        """
        tg = (TeamGame
              .select(fn.max(TeamGame.round_num))
              .where(TeamGame.team == self,
                     TeamGame.is_bye == False)
              .get())
        last_round = tg.round_num or 0
        cg = (TournGame
              .select()
              .where((TournGame.team1 == self) |
                     (TournGame.team2 == self))
              .where(TournGame.table_num.is_null(False),
                     TournGame.round_num > last_round)
              .order_by(TournGame.round_num))
        return cg[0] if len(cg) > 0 else None

    @property
    def current_playoff_game(self) -> BaseModel:
        """Return current TournGame for team (only if round robin stage is active)
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.SEMIS_BRACKET:
            return None

        if tourn.stage_compl < TournStage.FINALS_BRACKET:
            if not self.playoff_team:
                return None
            bracket = Bracket.SEMIS
        else:
            if not self.finals_team:
                return None
            bracket = Bracket.FINALS

        query = (PlayoffGame
                 .select()
                 .where((PlayoffGame.team1 == self) |
                        (PlayoffGame.team2 == self))
                 .where(PlayoffGame.bracket == bracket)
                 .order_by(PlayoffGame.round_num))
        wins = [0, 0]
        for game in query.iterator():
            if not game.winner:
                return game
            win_idx = bool(game.winner == game.team2_name)
            wins[win_idx] += 1
            if max(wins) > 1:
                break
        return None

    @property
    def playoff_status(self) -> str:
        """For the Final Four view.  Note, this call is only valid for actual final four
        teams (garbage will be returned for non-playoff teams).
        """
        if self.playoff_match_wins == 2:
            return "Champion"
        elif self.playoff_match_wins == 1:
            return "Finalist"
        else:
            return "Semifinalist"

    def get_games(self, all_games: bool = False) -> list[BaseModel]:
        """Get completed TournGame records (including possible byes up to the current
        round for the stage).
        """
        cur_round = TournGame.current_round()
        if cur_round == 0:
            return None  # as distinct from [], e.g. game 1 in progress
        query = (TournGame
                 .select()
                 .where((TournGame.team1 == self) |
                        (TournGame.team2 == self))
                 .order_by(TournGame.round_num))
        if cur_round != -1 and not all_games:
            query = query.where(TournGame.round_num <= cur_round)
        return list(query)

    def get_playoff_games(self, bracket: Bracket, all_games: bool = False) -> list[BaseModel]:
        """Get completed PlayoffGame records.
        """
        if not all_games:
            raise ImplementationError("`all_games=False` not yet implemented")
        tourn = TournInfo.get()
        if bracket == Bracket.SEMIS:
            if tourn.stage_compl < TournStage.SEMIS_BRACKET:
                return None
        else:
            assert bracket == Bracket.FINALS
            if tourn.stage_compl < TournStage.FINALS_BRACKET:
                return None

        query = (PlayoffGame
                 .select()
                 .where(PlayoffGame.bracket == bracket)
                 .where((PlayoffGame.team1 == self) |
                        (PlayoffGame.team2 == self))
                 .order_by(PlayoffGame.round_num))
        return list(query)

    def get_opps_games(self, opps: list[Self]) -> list[BaseModel]:
        """Get TournGame records for all games versus specified opponents
        """
        query = (TournGame
                 .select()
                 .join(TeamGame, on=(TeamGame.game_label == TournGame.label))
                 .where(TeamGame.team == self,
                        TeamGame.opponent.in_(opps)))
        return list(query)

#############
# TournGame #
#############

class TournGame(UIMixin, BaseTournGame):
    """
    """
    team1 = ForeignKeyField(Team, column_name='team1_id')
    team2 = ForeignKeyField(Team, column_name='team2_id', null=True)

    class Meta:
        table_name = BaseTournGame._meta.table_name

    @classmethod
    def current_round(cls) -> int:
        """Return the current round of play, with the special values of `0` to indicate
        that the round robin brackets have not yet been created, and `-1` to indicate that
        the round robin stage is complete.
        """
        tourn = TournInfo.get()
        if tourn.stage_compl < TournStage.TOURN_BRACKET:
            return 0

        round_games = tourn.teams // 2
        query = (cls
                 .select(cls.round_num, fn.count(cls.id))
                 .where(cls.winner.is_null(False))
                 .group_by(cls.round_num)
                 .order_by(cls.round_num.desc()))
        if not query:
            return 1  # no games yet played
        round_num, ngames = query.scalar(as_tuple=True)

        if ngames < round_games:
            return round_num
        if round_num < tourn.tourn_rounds:
            return round_num + 1
        return -1

    @classmethod
    def phase_status(cls) -> str:
        """Return current status of the round robin phase (for mobile UI).
        """
        cur_round = cls.current_round()
        if cur_round == 0:
            return "Not Started"
        elif cur_round == -1:
            return "Done"
        else:
            return f"Round {cur_round}"

    @property
    def bracket_ident(self) -> str:
        """Display name for the bracket
        """
        return BRACKET_NAME[Bracket.TOURN]

    @property
    def team_seeds(self) -> str:
        """
        """
        tm_seeds = (self.team1_div_seed, self.team2_div_seed)
        return ' vs. '.join(str(x) for x in tm_seeds if x)

    @property
    def team_tags(self) -> tuple[str, str]:
        """Team tags with embedded HTML annotation (used for bracket and scores/results
        displays)--currently, can only be called for actual matchup, and not bye records
        """
        assert self.team1 and self.team2
        return self.team1.team_tag, self.team2.team_tag

    @property
    def bye_tag(self) -> str:
        """Bye reference based on team tags with embedded HTML annotation (used for
        bracket and scores/results displays)--currently, can only be called for bye
        records
        """
        assert self.team1 and self.team2 is None  # ...or return None?
        return self.team1.team_tag

    @property
    def winner_info(self) -> tuple[str, int, int]:
        """Returns tuple(name, div_seed, pts)
        """
        if self.team1_name == self.winner:
            return self.team1_name, self.team1_div_seed, self.team1_pts
        else:
            return self.team2_name, self.team2_div_seed, self.team2_pts

    @property
    def loser_info(self) -> tuple[str, int, int]:
        """Returns tuple(name, div_seed, pts)
        """
        if self.team1_name == self.winner:
            return self.team2_name, self.team2_div_seed, self.team2_pts
        else:
            return self.team1_name, self.team1_div_seed, self.team1_pts

    def team_idx(self, team: Team) -> int:
        """Return the team index for the specified team: `0`, `1`, or `-1`, representing
        team1, team2, or a bye (respectively).  This is used to map into `team_tags`.
        """
        if team == self.team1:
            return 0 if self.table_num else -1
        if team == self.team2:
            return 1 if self.table_num else -1
        raise LogicError(f"team '{team.team_name}' not in tourn_game '{self.label}'")

    def team_info(self, team: Team) -> tuple[str, int, int]:
        """Returns tuple(name, div_seed, pts)
        """
        if self.is_winner(team):
            return self.winner_info
        else:
            return self.loser_info

    def opp_info(self, team: Team) -> tuple[str, int, int]:
        """Returns tuple(name, div_seed, pts)
        """
        if self.is_winner(team):
            return self.loser_info
        else:
            return self.winner_info

    def is_winner(self, team: Team) -> bool:
        """Cleaner interface for use in templates
        """
        return team.team_name == self.winner

###############
# PlayoffGame #
###############

class PlayoffGame(UIMixin, BasePlayoffGame):
    """
    """
    team1 = ForeignKeyField(Team, column_name='team1_id')
    team2 = ForeignKeyField(Team, column_name='team2_id')

    class Meta:
        table_name = BasePlayoffGame._meta.table_name

    @classmethod
    def current_round(cls, bracket: Bracket) -> int:
        """Return the current round of play, with the special values of `0` to indicate
        that the specified playoff bracket has not yet been created, and `-1` to indicate
        that the associated playoff stage is complete.  Note that "round", for playoff
        brackets, means the lowest active game number for any matchup in the stage.
        """
        compl = cls.bracket_complete(bracket)
        if compl is None:
            return 0
        elif compl:
            return -1

        query = (cls
                 .select(cls.matchup_num, fn.count(cls.winner))
                 .where(cls.bracket == bracket)
                 .group_by(cls.matchup_num)
                 .order_by(fn.count(cls.winner).asc()))
        matchup_num, ngames = query.scalar(as_tuple=True)

        assert ngames < 3
        return ngames + 1

    @classmethod
    def phase_status(cls, bracket: Bracket) -> str:
        """Return current status of the playoff round phase (for mobile UI).
        """
        cur_round = cls.current_round(bracket)
        if cur_round == 0:
            return "Not Started"
        elif cur_round == -1:
            return "Done"
        else:
            # see docheader for `current_round()` on terminology here
            return f"Game {cur_round}"

    @classmethod
    def bracket_complete(cls, bracket: Bracket) -> bool:
        """Check if all play associated with the specified bracket is complete.  `None`
        indicates that the bracket has not started, whereas `False` indicates that play
        has started but not yet complete.

        Must be called after `update_team_stats()` for the most recent game.
        """
        tourn = TournInfo.get()
        if bracket == Bracket.SEMIS:
            if tourn.stage_compl < TournStage.SEMIS_BRACKET:
                return None
        else:
            assert bracket == Bracket.FINALS
            if tourn.stage_compl < TournStage.FINALS_BRACKET:
                return None

        query = Team.select(fn.sum(Team.playoff_match_wins))
        match_wins = query.scalar()
        if match_wins > 3:
            raise DataError(f"too many playoff match wins ({match_wins})")

        if bracket == Bracket.SEMIS:
            return match_wins >= 2
        else:
            assert bracket == Bracket.FINALS
            return match_wins == 3

    @property
    def bracket_ident(self) -> str:
        """Display name for the bracket
        """
        return BRACKET_NAME[self.bracket]

    @property
    def matchup_ident(self) -> str:
        """Identifier for the matchup
        """
        return f"{self.bracket}-{self.matchup_num}"

    @property
    def team_ranks(self) -> str:
        """Show matchup of tournament (after round robin) rankings.
        """
        tm_ranks = (self.team1.tourn_rank, self.team2.tourn_rank)
        return ' vs. '.join(str(x) for x in tm_ranks if x)

    @property
    def team_tags(self) -> tuple[str, str]:
        """Team tags with embedded HTML annotation (used for bracket and scores/results
        displays).
        """
        assert self.team1 and self.team2
        return self.team1.team_tag_pl, self.team2.team_tag_pl

    def team_idx(self, team: Team) -> int:
        """Return the team index for the specified team.  This is used to map into
        `team_tags`.
        """
        return bool(team == self.team2)

##############
# PlayerGame #
##############

class PlayerGame(UIMixin, BasePlayerGame):
    """Denormalization of SeedGame (and possibly TournGame data), for use in computing
    stats, determining head-to-head match-ups, etc.
    """
    player = ForeignKeyField(Player, field='player_num', column_name='player_num')

    class Meta:
        table_name = BasePlayerGame._meta.table_name

############
# TeamGame #
############

class TeamGame(UIMixin, BaseTeamGame):
    """Denormalization of TournGame data, for use in computing stats, determining
    head-to-head match-ups, etc.
    """
    team     = ForeignKeyField(Team)
    opponent = ForeignKeyField(Team, column_name='opp_id', null=True)

    class Meta:
        table_name = BaseTeamGame._meta.table_name

#############
# PostScore #
#############

class PostScore(UIMixin, BasePostScore):
    """
    """
    posted_by = ForeignKeyField(Player, field='player_num', column_name='posted_by_num')
    ref_score = ForeignKeyField('self', null=True)

    class Meta:
        table_name = BasePostScore._meta.table_name

######################
# more utility stuff #
######################

# NOTE: this stuff here depends on types created above

BRACKET_GAME_CLS = {
    Bracket.SEED  : SeedGame,
    Bracket.TOURN : TournGame,
    Bracket.SEMIS : PlayoffGame,
    Bracket.FINALS: PlayoffGame
}

def get_bracket(label: str) -> str:
    """Get bracket for the specified game label.  FIX: quick and dirty for now--need a
    proper representations of bracket definitions overall!!!
    """
    pfx = label.split('-', 1)[0]
    assert pfx in (Bracket.SEED, Bracket.TOURN, Bracket.SEMIS, Bracket.FINALS)
    return pfx

def get_game_by_label(label: str) -> SeedGame | TournGame:
    """Use a little ORM knowledge to fetch from the appropriate table--LATER: can put this
    in the right place (or refactor the whole bracket-game thing)!!!
    """
    game_cls = BRACKET_GAME_CLS.get(get_bracket(label))
    query = (game_cls
             .select()
             .where(game_cls.label == label))
    return query.get_or_none()
