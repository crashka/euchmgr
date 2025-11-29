# -*- coding: utf-8 -*-

import re
from datetime import datetime, date

from peewee import SqliteDatabase, Model, DateTimeField
from playhouse.sqlite_ext import SqliteExtDatabase

from core import DataFile

#####################
# utility functions #
#####################

TIME_FMT = '%Y-%m-%d %H:%M:%S'

def now_str() -> str:
    """Readable format that works for string comparisons
    """
    return datetime.now().strftime(TIME_FMT)

############
# database #
############

DB_FILETYPE = '.sqlite3'

pragmas = {'journal_mode'            : 'wal',
           'cache_size'              : -1 * 64000,  # 64MB
           'foreign_keys'            : 1,
           'ignore_check_constraints': 0,
           'synchronous'             : 0}

db = SqliteExtDatabase(None, pragmas=pragmas)

def db_init(db_name: str) -> None:
    """Initialize database for specified name.
    """
    db_file = f'{db_name}{DB_FILETYPE}'
    db.init(DataFile(db_file))
    db.db_name = db_name  # little hack to remember name

def db_name() -> str:
    """Second half of little hack (see above)
    """
    return db.db_name

def db_connect() -> None:
    """Connect to database (needed before any database operations)
    """
    if db.is_closed():
        db.connect()

#############
# BaseModel #
#############

class BaseModel(Model):
    """Base model for this module, with defaults and system columns
    """
    # system columns
    created_at = DateTimeField(default=now_str)
    updated_at = DateTimeField()

    def save(self, *args, **kwargs):
        if not self.updated_at:
            self.updated_at = self.created_at
        elif 'updated_at' not in self._dirty:
            self.updated_at = now_str()
        return super().save(*args, **kwargs)

    class Meta:
        database = db
        legacy_table_names = False
        only_save_dirty = True
