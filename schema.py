#!/usr/bin/env python
# -*- coding: utf-8 -*-

from typing import ClassVar
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

    @classmethod
    def get_by_name(cls, name: str) -> 'TournInfo':
        """Convenience query method
        """
        return cls.get(cls.name == name)

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
    partner        = ForeignKeyField('self', field='player_num', column_name='partner',
                                     object_id_name='partner_num', null=True)
    partner2       = ForeignKeyField('self', field='player_num', column_name='partner2',
                                     object_id_name='partner2_num', null=True)
    picked_by      = ForeignKeyField('self', field='player_num', column_name='picked_by',
                                     object_id_name='picked_by_num', null=True)

    # class variables
    player_map: ClassVar[dict[int, 'Player']] = None

    class Meta:
        indexes = (
            (('last_name', 'first_name'), True),
        )

    @classmethod
    def get_player_map(cls, requery: bool = False) -> dict[int, 'Player']:
        """Return dict of all players, indexed by player_num
        """
        if cls.player_map and not requery:
            return cls.player_map

        cls.player_map = {}
        for p in cls.select():
            cls.player_map[p.player_num] = p
        return cls.player_map

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

class SeedGame(BaseModel):
    """
    """
    # required info
    round_num      = IntegerField()
    table_num      = IntegerField()
    label          = TextField(unique=True)  # rnd-tbl
    player1        = ForeignKeyField(Player, field='player_num', column_name='player1',
                                     object_id_name='player1_num')
    player2        = ForeignKeyField(Player, field='player_num', column_name='player2',
                                     object_id_name='player2_num', null=True)
    player3        = ForeignKeyField(Player, field='player_num', column_name='player3',
                                     object_id_name='player3_num', null=True)
    player4        = ForeignKeyField(Player, field='player_num', column_name='player4',
                                     object_id_name='player4_num', null=True)
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

########
# Team #
########

class Team(BaseModel):
    """
    """
    # required info
    player1        = ForeignKeyField(Player, field='player_num', column_name='player1',
                                     object_id_name='player1_num')
    player2        = ForeignKeyField(Player, field='player_num', column_name='player2',
                                     object_id_name='player2_num')
    player3        = ForeignKeyField(Player, field='player_num', column_name='player3',
                                     object_id_name='player3_num', null=True)
    is_thm         = BooleanField(default=False)
    is_bye         = BooleanField(default=False)
    team_name      = TextField(unique=True)
    avg_player_seed = FloatField()
    team_seed      = IntegerField(unique=True)  # 1-based, based on avg_player_seed
    div_num        = IntegerField()
    div_seed       = IntegerField()
    # tournament play
    tourn_wins     = IntegerField(null=True)
    tourn_losses   = IntegerField(null=True)
    tourn_pts_for  = IntegerField(null=True)
    tourn_pts_against = IntegerField(null=True)
    tourn_rank     = IntegerField(null=True)

#############
# TournGame #
#############

class TournGame(BaseModel):
    """
    """
    # required info
    div_num        = IntegerField()
    round_num      = IntegerField()
    table_num      = IntegerField()
    label          = TextField(unique=True)     # div-rnd-tbl
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
    player         = ForeignKeyField(Player, field='player_num', column_name='player',
                                     object_id_name='player_num')
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
