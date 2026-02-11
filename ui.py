# -*- coding: utf-8 -*-

from typing import Self, Iterator

from peewee import fn

from database import BaseModel
from schema import TournStage, TournInfo, Player, SeedGame, PlayerGame

###########
# UIMixin #
###########

class UIMixin:
    """Mixin to support compatibility with base schema instances.
    """
    def __hash__(self):
        """Use the hash of the base schema class (requires module classes to inherit from
        this mixin then the schema class).
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

############
# UIPlayer #
############

EMPTY_PLYR_STATS = {
    'seed_wins'       : None,
    'seed_losses'     : None,
    'seed_pts_for'    : None,
    'seed_pts_against': None
}

class UIPlayer(UIMixin, Player):
    """Represents a player in the tournament, as well as a mobile (i.e. non-admin) user of
    the app.
    """
    class Meta:
        table_name = Player._meta.table_name

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
        # see NOTE below (in get_game_stats())
        opps_nums = [pl.player_num for pl in opps]
        query = query.where((PlayerGame.opponents.extract_text('0').in_(opps_nums)) |
                            (PlayerGame.opponents.extract_text('1').in_(opps_nums)))
        return list(query)

class PlayerRegister(Player):
    """Subclass of `Player` that represents the process of player registration process.
    Note that the cached player map is avoided in all calls, to avoid integrity problems.
    """
    class Meta:
        table_name = Player._meta.table_name

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

class PartnerPick(Player):
    """Subclass of `Player` that represents the process of picking partners.  Note that
    the cached player map is avoided in all calls, to avoid integrity problems.
    """
    class Meta:
        table_name = Player._meta.table_name

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
        pl_query = Player.select()
        avail = list(filter(lambda x: x.available, pl_query))
        if not avail:
            return []
        assert len(avail) > 1
        return sorted(avail, key=lambda x: x.player_rank)[1:]

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

