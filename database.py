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

def db_init(name: str) -> SqliteDatabase:
    """Initialize database for the specified name (if not already bound); return the
    Peewee `Database` object.

    Note that we are using autoconnect, since there is no reason to explicitly open or
    close connections (as long as we are not switching databases).

    """
    if not name:
        raise RuntimeError("Database name not specified")
    cur_db = db_name()
    if cur_db and name == cur_db:
        return db

    db_file = f'{name}{DB_FILETYPE}'
    db.init(DataFile(db_file))
    setattr(db, 'db_name', name)  # little hack to remember name
    return db

def db_name() -> str | None:
    """Second half of little hack (see above)
    """
    return getattr(db, 'db_name', None)

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
