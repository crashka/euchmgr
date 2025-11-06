#!/usr/bin/env python
# -*- coding: utf-8 -*-

from typing import ClassVar, Self, Iterator
import re

from peewee import (TextField, IntegerField, BooleanField, ForeignKeyField, FloatField,
                    OperationalError)
from playhouse.sqlite_ext import JSONField

from database import BaseModel

DFLT_SEED_ROUNDS  = 8
DFLT_TOURN_ROUNDS = 8
DFLT_DIVISIONS    = 2

#############
# TournInfo #
#############

class TournInfo(BaseModel):
    """
    """
    name           = TextField(unique=True)
    timeframe      = TextField(null=True)
    venue          = TextField(null=True)
    players        = IntegerField(null=True)
    teams          = IntegerField(null=True)
    thm_teams      = IntegerField(default=0)
    seed_rounds    = IntegerField(default=DFLT_SEED_ROUNDS)
    tourn_rounds   = IntegerField(default=DFLT_TOURN_ROUNDS)
    divisions      = IntegerField(default=DFLT_DIVISIONS)

    # class variables
    inst: ClassVar[Self] = None  # singleton instance

    @classmethod
    def get(cls, requery: bool = False) -> Self:
        """Return cached singleton instance (shadows more general base class method).
        """
        # NOTE: use iterator() to circumvent caching in ORM layer
        res = [t for t in cls.select().limit(2).iterator()]
        assert len(res) == 1  # fails if not initialized, or unexpected multiple records

        if cls.inst is None or requery:
            cls.inst = res[0]
        return cls.inst

##########
# Player #
##########

class Player(BaseModel):
    """
    """
    # required info
    first_name     = TextField()
    last_name      = TextField()
    nick_name      = TextField(unique=True)  # defaults to last_name
    reigning_champ = BooleanField(default=False)
    player_num     = IntegerField(unique=True)  # 1-based random number
    # seeding round
    seed_wins      = IntegerField(null=True)
    seed_losses    = IntegerField(null=True)
    seed_win_pct   = FloatField(null=True)
    seed_pts_for   = IntegerField(null=True)
    seed_pts_against = IntegerField(null=True)
    seed_pts_diff  = IntegerField(null=True)
    seed_pts_pct   = FloatField(null=True)
    player_seed    = IntegerField(unique=True, null=True)  # 1-based
    # partner picks
    partner        = ForeignKeyField('self', field='player_num', column_name='partner_num',
                                     null=True)
    partner2       = ForeignKeyField('self', field='player_num', column_name='partner2_num',
                                     null=True)
    picked_by      = ForeignKeyField('self', field='player_num', column_name='picked_by_num',
                                     null=True)

    # class variables
    player_map: ClassVar[dict[int, Self]] = None  # indexed by player_num

    class Meta:
        indexes = (
            (('last_name', 'first_name'), True),
        )

    @classmethod
    def get_player_map(cls, requery: bool = False) -> dict[int, Self]:
        """Return dict of all players, indexed by player_num
        """
        if cls.player_map and not requery:
            return cls.player_map

        cls.player_map = {}
        # see NOTE on use of iterator in `TournInfo.get`, above
        for p in cls.select().iterator():
            cls.player_map[p.player_num] = p
        return cls.player_map

    @classmethod
    def get_player(cls, player_num: int) -> Self:
        """Return player by player_num (from cached map)
        """
        pl_map = cls.get_player_map()
        return pl_map[player_num]

    def pick_partners(self, partner1: Self, partner2: Self = None) -> None:
        """
        """
        print(f"player: {self.player_num} ({self.nick_name})")
        print(f"  - picks partner {partner1.player_num} ({partner1.nick_name})")
        assert self.partner_num is None
        assert partner1.picked_by_num is None
        self.partner_num = partner1.player_num
        partner1.picked_by_num = self.player_num

        if partner2:
            print(f"  - picks partner {partner2.player_num} ({partner2.nick_name})")
            assert self.partner2_num is None
            assert partner2.picked_by_num is None
            self.partner2_num = partner2.player_num
            partner2.picked_by_num = self.player_num

    def save(self, *args, **kwargs):
        """Ensure that nick_name is not null, since it is used as the display name in
        brackets (defaults to last_name if not otherwise specified)
        """
        if not self.nick_name:
            self.nick_name = self.last_name
        return super().save(*args, **kwargs)

############
# SeedGame #
############

GAME_PTS = 10

class SeedGame(BaseModel):
    """
    """
    # required info
    round_num      = IntegerField()
    table_num      = IntegerField()
    label          = TextField(unique=True)  # seed-{rnd}-{tbl}
    player1        = ForeignKeyField(Player, field='player_num', column_name='player1_num')
    player2        = ForeignKeyField(Player, field='player_num', column_name='player2_num',
                                     null=True)
    player3        = ForeignKeyField(Player, field='player_num', column_name='player3_num',
                                     null=True)
    player4        = ForeignKeyField(Player, field='player_num', column_name='player4_num',
                                     null=True)
    team1_name     = TextField(null=True)  # player1_name / player2_name
    team2_name     = TextField(null=True)  # player3_name / player4_name
    byes           = TextField(null=True)  # player1 / ...
    # results
    team1_pts      = IntegerField(null=True)
    team2_pts      = IntegerField(null=True)
    winner         = TextField(null=True)  # team name

    class Meta:
        indexes = (
            (('round_num', 'table_num'), True),
        )

    def add_scores(self, team1_pts: int, team2_pts: int) -> None:
        """Record scores for completed (or incomplete) game.  Scores should not be updated
        directly in model object, since denormalizations (e.g. in PlayerGame) will not be
        maintained (without some more involved pre-save logic).

        TODO: check to see if this overwrites a completed game result, in which case the
        denorms need to be properly managed!!!
        """
        self.team1_pts = team1_pts
        self.team2_pts = team2_pts

        if self.team1_pts >= GAME_PTS:
            assert self.team2_pts < GAME_PTS
            self.winner = self.team1_name
        elif self.team2_pts >= GAME_PTS:
            self.winner = self.team2_name
        else:
            self.winner = None

        # TODO: insert records into PlayerGame!!!
        pass

########
# Team #
########

class Team(BaseModel):
    """
    """
    # required info
    player1        = ForeignKeyField(Player, field='player_num', column_name='player1_num')
    player2        = ForeignKeyField(Player, field='player_num', column_name='player2_num')
    player3        = ForeignKeyField(Player, field='player_num', column_name='player3_num',
                                     null=True)
    is_thm         = BooleanField(default=False)
    team_name      = TextField(unique=True)
    avg_player_seed = FloatField()
    top_player_seed = IntegerField()
    # tournament bracket
    team_seed      = IntegerField(unique=True, null=True)  # 1-based, from players seeds
    div_num        = IntegerField(null=True)
    div_seed       = IntegerField(null=True)
    # tournament play
    tourn_wins     = IntegerField(null=True)
    tourn_losses   = IntegerField(null=True)
    tourn_win_pct  = FloatField(null=True)
    tourn_pts_for  = IntegerField(null=True)
    tourn_pts_against = IntegerField(null=True)
    tourn_pts_diff = IntegerField(null=True)
    tourn_pts_pct  = FloatField(null=True)
    tourn_rank     = IntegerField(null=True)

    # class variables
    team_map: ClassVar[dict[int, Self]] = None  # indexed by team_seed

    class Meta:
        indexes = (
            (('div_num', 'div_seed'), True),
        )

    @classmethod
    def get_team_map(cls, requery: bool = False) -> dict[int, Self]:
        """Return dict of all teams, indexed by team_seed
        """
        if cls.team_map and not requery:
            return cls.team_map

        cls.team_map = {}
        # see NOTE on use of iterator in `TournInfo.get`, above
        for t in cls.select().iterator():
            assert t.team_seed  # late check that seeds have been set
            cls.team_map[t.team_seed] = t
        return cls.team_map

    @classmethod
    def get_div_map(cls, div: int, requery: bool = False) -> dict[int, Self]:
        """Return dict of division teams, indexed by div_seed
        """
        tm_list = cls.get_team_map(requery).values()
        return {t.div_seed: t for t in tm_list if t.div_num == div}

    @classmethod
    def iter_teams(cls) -> Iterator[Self]:
        """Iterator for teams (wrap ORM details)
        """
        # see NOTE on use of iterator in `TournInfo.get`, above
        for t in cls.select().iterator():
            yield t

#############
# TournGame #
#############

class TournGame(BaseModel):
    """
    """
    # required info
    div_num        = IntegerField()
    round_num      = IntegerField()
    table_num      = IntegerField(null=True)  # null if bye
    label          = TextField(unique=True)   # rr-{div}-{rnd}-{tbl}
    team1_seed     = IntegerField()
    team2_seed     = IntegerField()
    team1_name     = TextField()
    team2_name     = TextField()
    team1_div_seed = IntegerField()
    team2_div_seed = IntegerField()
    # results
    team1_pts      = IntegerField(null=True)
    team2_pts      = IntegerField(null=True)
    winner         = TextField(null=True)  # team name

    class Meta:
        indexes = (
            (('div_num', 'round_num', 'table_num'), True),
        )

    def add_scores(self, team1_pts: int, team2_pts: int) -> None:
        """Record scores for completed (or incomplete) game.  Scores should not be updated
        directly in model object, since denormalizations (e.g. in PlayerGame) will not be
        maintained (without some more involved pre-save logic).

        TODO: check to see if this overwrites a completed game result, in which case the
        denorms need to be properly managed!!!
        """
        self.team1_pts = team1_pts
        self.team2_pts = team2_pts

        if self.team1_pts >= GAME_PTS:
            assert self.team2_pts < GAME_PTS
            self.winner = self.team1_name
        elif self.team2_pts >= GAME_PTS:
            self.winner = self.team2_name
        else:
            self.winner = None

        # TODO: insert records into TeamGame!!!
        pass

##############
# PlayerGame #
##############

class PlayerGame(BaseModel):
    """Denormalization of SeedGame and TournGame data, for use in computing stats,
    determining head-to-head match-ups, etc.
    """
    bracket        = TextField()             # "seed", "rr", or "final"
    round_num      = IntegerField()
    game_label     = TextField(unique=True)  # seed-rnd-tbl or rr-div-rnd-tbl
    player         = ForeignKeyField(Player, field='player_num', column_name='player_num')
    partners       = JSONField(null=True)    # array of partner player_num(s)
    opponents      = JSONField(null=True)    # array of opposing player_nums
    player_team    = TextField(null=True)
    opp_team       = TextField(null=True)    # or "bye"(?)
    is_bye         = BooleanField(null=True)
    # results
    team_pts       = IntegerField(null=True)
    opp_pts        = IntegerField(null=True)
    is_winner      = BooleanField(null=True)

    class Meta:
        indexes = (
            (('bracket', 'round_num', 'player'), True),
        )

##########
# create #
##########

ALL_MODELS = [TournInfo, Player, SeedGame, Team, TournGame, PlayerGame]

def schema_create(models: list[BaseModel | str] | str = None, force = False) -> None:
    """Create tables for specified models (list of objects or comma-separated list of
    names), or all models if no list is specified.
    """
    if models is None:
        models = ALL_MODELS
    elif isinstance(models, str):
        models = models.split(',')
    assert isinstance(models, list)
    if isinstance(models[0], str):
        models_new = []
        for model in models:
            if model not in globals():
                raise RuntimeError(f"Model {model} not imported")
            model_obj = globals()[model]
            if not issubclass(model_obj, BaseModel):
                raise RuntimeError(f"Model {model} must be subclass of `BaseModel`")
            models_new.append(model_obj)
        models = models_new

    # TEMP: just drop all tables, so we don't have to worry about integrity, cascading
    # deletes, legacy data, etc.
    if force:
        for model in reversed(models):
            model.drop_table()

    for model in models:
        try:
            model.create_table(safe=False)
        except OperationalError as e:
            if re.fullmatch(r'table "(\w+)" already exists', str(e)) and force:
                model.drop_table(safe=False)
                model.create_table(safe=False)
            else:
                raise
