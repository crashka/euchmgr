# -*- coding: utf-8 -*-

import re
from datetime import datetime, date
import os.path

from peewee import SqliteDatabase, Model, DateTimeField
from playhouse.sqlite_ext import CSqliteExtDatabase

from core import DataFile, log, DEBUG, LogicError

#####################
# utility functions #
#####################

TIME_FMT = '%Y-%m-%d %H:%M:%S'

def now_str() -> str:
    """Readable format that works for string comparisons.
    """
    return datetime.now().strftime(TIME_FMT)

# count of SQL statements, by SQL command
Tally = dict[str, int]
TOTAL = 'total'
SQL_TALLY: Tally = {TOTAL : 0}

def trace_sql_callback(sql_stmt) -> None:
    """Currently just log at level 'debug'.
    """
    log.debug(f"SQL: {sql_stmt}")
    sql_cmd = sql_stmt.split(' ', 1)[0].lower()
    if sql_cmd not in SQL_TALLY:
        SQL_TALLY[sql_cmd] = 0
    SQL_TALLY[sql_cmd] += 1
    SQL_TALLY[TOTAL] += 1

def get_sql_tally(baseline: Tally = None) -> Tally | tuple[Tally, Tally]:
    """Return tally of SQL statements, by SQL command.  If `baseline` is passed in, return
    a tuple of the aggregate as well as increment counts.
    """
    cur_tally = SQL_TALLY.copy()
    if not baseline:
        return cur_tally

    incr_tally = {cmd: 0 for cmd in baseline}
    for cmd in cur_tally:
        incr_tally[cmd] = cur_tally[cmd] - baseline.get(cmd, 0)
    return cur_tally, incr_tally

############
# database #
############

DB_FILETYPE = '.tourn_db'

# note that sharing connections across threads removes some integrity checks
shared_conn = False

pragmas = {'journal_mode'            : 'wal',
           'cache_size'              : -1 * 64000,  # 64MB
           'foreign_keys'            : 1,
           'ignore_check_constraints': 0,
           'synchronous'             : 0}

db_params = {'c_extensions'     : True,
             'autoconnect'      : False,
             'thread_safe'      : not shared_conn,
             'check_same_thread': not shared_conn}

# start in "deferred" mode
db = CSqliteExtDatabase(None, pragmas=pragmas, **db_params)

def db_filepath(name: str, db_dir: str = None) -> str:
    """Build filename (or pathname) based on specified name.
    """
    db_file = f'{name}{DB_FILETYPE}'
    if db_dir:
        return DataFile(db_file, db_dir)
    else:
        return DataFile(db_file)

def db_init(name: str, force: bool = False, trace_sql: bool = False) -> SqliteDatabase:
    """Initialize database for the specified name (if not already bound); return the ORM
    `Database` object (to discourage importing `db` directly).  Use the `force` flag if
    okay to overwrite an existing database file.  Implicitly connects to the database
    (cleaner client call sequence).

    The `trace_sql` flag enables logging of SQL statements (at level `debug`), as well as
    tallying SQL statements by SQL command (see get_sql_tally, above).  REVISIT: should we
    put this flag on db_connect() instead???

    Note that we are NOT using autoconnect (for more disciplined state management), so we
    need to explcitly open and close connections (whether done on a per-request basis by
    the caller, or internally here to keep them open and reusable for the duration of the
    database session).
    """
    if not name:
        raise RuntimeError("Database name not specified")

    db_file = db_filepath(name)
    if not force:
        # TODO: convert to proper exceptions!!!
        assert not db_name()
        assert not db_is_initialized()
        assert not os.path.exists(db_file)
    else:
        # probably don't really have to do this, but is a little cleaner
        db_close()
    db.init(db_file)
    setattr(db, 'db_name', name)  # little hack to remember name
    db_connect(name)  # REVISIT: should we require this to be explicit???
    if DEBUG and trace_sql:
        db._state.conn.set_trace_callback(trace_sql_callback)
    log.debug(f"db_init({name}, force={force})")
    return db

def db_name() -> str | None:
    """Second half of little hack (see above).
    """
    return getattr(db, 'db_name', None)

def db_reset(force: bool = False) -> bool:
    """Reset database to a "deferred" state (i.e. not associated with a file, and not
    able to accept connections).
    """
    if not force:
        assert db_name()
        assert db_is_initialized()
        assert db_is_closed()
        delattr(db, 'db_name')
    else:
        # same as above (db_init)
        db_close()
        if hasattr(db, 'db_name'):
            delattr(db, 'db_name')
    db.init(None)
    log.debug(f"db_reset(force={force})")
    return True

def db_is_initialized() -> bool:
    """Whether the database has been initialized (i.e. database file specified, and able
    to accept connections).
    """
    return not db.deferred  # this is the flag peewee uses internally

def db_connect(name: str | None = None) -> bool:
    """Return `True` if connected to database (`False` if database is not initalized).
    """
    if name:
        cur_db = db_name()
        if not cur_db:
            db_init(name, force=True)  # FIX: ugly recursion here!!!
            log.debug(f"db_connect({name}), cur_db empty, called db_init")
            return True
        elif cur_db != name:
            raise LogicError(f"name ('{name}') does not match db_name() ('{cur_db}')")
        else:
            # TODO: log this condition for better understanding (we get here as part of
            # the ugly recursion, mentioned above--but what else?)!!!
            log.debug(f"db_connect({name}), cur_db = {cur_db}")
            pass
    elif not db_is_initialized():
        log.debug(f"db_connect({name}), db not initialized")
        return False
    db.connect(reuse_if_open=shared_conn)
    log.debug(f"db_connect({name}), db connected")
    return True

def db_close() -> SqliteDatabase:
    """Ensure that the current database is closed (e.g. for checkpointing the WAL); return
    the ORM `Database` object for convenience (see note in `db_init`).  Note that this
    call is idempotent.
    """
    if not db.is_closed():
        db.close()
        log.debug("db_close()")
    else:
        # TODO: log this condition (understand when/why it happens)!!!
        log.debug("db_close(), already closed")
    return db

def db_is_closed() -> bool:
    """Whether the database is closed (i.e. not able to perform SQL operations).
    """
    return db.is_closed()

#############
# BaseModel #
#############

class BaseModel(Model):
    """Base model for `schema` module entities.  Contains support for system columns and
    entity subclassing.
    """
    # system columns
    created_at = DateTimeField(default=now_str)
    updated_at = DateTimeField()

    class Meta:
        database = db
        legacy_table_names = False
        only_save_dirty = True

    __hash__ = Model.__hash__

    def __eq__(self, other):
        """Handle the case of comparing against a subclass instance.
        """
        return (
            (other.__class__ == self.__class__ or
             issubclass(other.__class__, self.__class__)) and
            self._pk is not None and
            self._pk == other._pk)

    def save(self, *args, **kwargs):
        """Support for system columns.
        """
        if not self._dirty:
            return False  # this is what peewee does if no dirty fields
        if not self.updated_at:
            self.updated_at = self.created_at
        elif 'updated_at' not in self._dirty:
            self.updated_at = now_str()
        return super().save(*args, **kwargs)
