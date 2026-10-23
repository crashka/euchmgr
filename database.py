#d -*- coding: utf-8 -*-

import re
from collections.abc import Callable
from datetime import datetime, date
from glob import glob
import os.path
from os import stat, stat_result, makedirs
import shutil

from peewee import SqliteDatabase, Model, DateTimeField
from playhouse.cysqlite_ext import CySqliteDatabase
from cysqlite import SQLITE_TRACE_PROFILE

from core import DATA_DIR, DataFile, config, profile, log, DEBUG

################
# module stuff #
################

cfg = config.config('database', profile)

#####################
# utility functions #
#####################

TIME_FMT = '%Y-%m-%d %H:%M:%S'

def now_str() -> str:
    """Readable format that works for string comparisons.
    """
    return datetime.now().strftime(TIME_FMT)

# return unixtime as an int (i.e. to the second)
unixtime = lambda: int(datetime.now().timestamp())

# count and timing of SQL statements, by SQL command
Tally = dict[str, int]
Timing = dict[str, float]  # rounded to tenths of milliseconds
TOTAL = 'total'
SQL_TALLY: Tally = {TOTAL : 0}
SQL_TIMING: Tally = {TOTAL : 0}  # "tally" of nanoseconds

def trace_sql_cb(event: int, sid: int, sql: str, ns: int) -> None:
    """Currently just log SQL statements at level 'debug'.
    """
    log.debug(f"SQL: {sql}")
    sql_cmd = sql.split(' ', 1)[0].lower()
    if sql_cmd not in SQL_TALLY:
        SQL_TALLY[sql_cmd] = 0
        SQL_TIMING[sql_cmd] = 0
    SQL_TALLY[sql_cmd] += 1
    SQL_TALLY[TOTAL] += 1
    SQL_TIMING[sql_cmd] += ns
    SQL_TIMING[TOTAL] += ns

def get_sql_tally(baseline: Tally = None) -> Tally | tuple[Tally, Tally]:
    """Return tally of SQL statements, by SQL command.  If `baseline` is passed in, return
    a tuple of the aggregate as well as incremental counts.
    """
    cur_tally = SQL_TALLY.copy()
    if not baseline:
        return cur_tally

    incr_tally = {cmd: 0 for cmd in baseline}
    for cmd in cur_tally:
        incr_tally[cmd] = cur_tally[cmd] - baseline.get(cmd, 0)
    return cur_tally, incr_tally

def get_sql_timing(baseline: Timing = None) -> Timing | tuple[Timing, Timing]:
    """Return SQL execution time (in ms), by SQL command.  If `baseline` is passed in,
    return a tuple of the aggregate as well as incremental time.  Note that underlying
    timing is at (something like) a millisecond granularity, so aggregates are not
    reliable for mostly fast statements.
    """
    timing_ms = lambda tm: {k: round(v / 1000000, 1) for k, v in tm.items()}
    cur_time = timing_ms(SQL_TIMING)  # makes a copy
    if not baseline:
        return cur_time

    incr_time = {cmd: 0.0 for cmd in baseline}
    for cmd in cur_time:
        incr_time[cmd] = cur_time[cmd] - baseline.get(cmd, 0.0)
    return cur_time, incr_time

############
# database #
############

DB_FILETYPE = '.tourn_db'
DB_SAVETYPE = '.chkpt_db'

# note that sharing connections across threads removes some integrity checks
shared_conn = False

pragmas = {'journal_mode' : 'wal',
           'cache_size'   : -1 * 64000,  # 64MB
           'foreign_keys' : 1,
           'synchronous'  : 1}

db_params = {'autoconnect': False,
             'thread_safe': not shared_conn,
             'lock_type'  : 'IMMEDIATE'}

# start in "deferred" mode
db = CySqliteDatabase(None, pragmas=pragmas, **db_params)

# expose useful attributes (discourage importing `db` directly)
db_connection_context = db.connection_context
db_atomic = db.atomic

def db_filepath(name: str, db_dir: str = None) -> str:
    """Build filename (or pathname) based on specified name.
    """
    db_file = f'{name}{DB_FILETYPE}'
    if db_dir:
        return DataFile(db_file, db_dir)
    else:
        return DataFile(db_file)

def db_savepath(save_tag: str, db_dir: str = None) -> str:
    """Build filename (or pathname) for saved database (e.g. checkpoint) based on database
    name and specified "tag".
    """
    name = f"{db_name()}-{save_tag}"
    db_file = f'{name}{DB_SAVETYPE}'
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
        db._state.conn.trace(trace_sql_cb, SQLITE_TRACE_PROFILE)
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
            log.trace(f"db_connect({name}), cur_db empty, called db_init")
            return True
        elif cur_db != name:
            raise ConnectionError(f"name ('{name}') does not match db_name() ('{cur_db}')")
        else:
            # TODO: log this condition for better understanding (we get here as part of
            # the ugly recursion, mentioned above--but what else?)!!!
            log.trace(f"db_connect({name}), cur_db = {cur_db}")
            pass
    elif not db_is_initialized():
        log.trace(f"db_connect({name}), db not initialized")
        return False
    db.connect(reuse_if_open=shared_conn)
    log.trace(f"db_connect({name}), db connected")
    return True

def db_close() -> SqliteDatabase:
    """Ensure that the current database is closed (e.g. for checkpointing the WAL); return
    the ORM `Database` object for convenience (see note in `db_init`).  Note that this
    call is idempotent.
    """
    if not db.is_closed():
        db.close()
        log.trace("db_close()")
    else:
        # TODO: log this condition (understand when/why it happens)!!!
        log.trace("db_close(), already closed")
    return db

def db_is_closed() -> bool:
    """Whether the database is closed (i.e. not able to perform SQL operations).
    """
    return db.is_closed()

def db_prepare() -> None:
    """Finish setting up newly created database.  For now, this just means archiving any
    previous checkpoint files with the same database name.
    """
    assert db_is_initialized()
    archive_tag = str(unixtime())
    archive_checkpoints(archive_tag)

# sequence of db checkpoints for a tournament, in chronological order
ChkptSeq = dict[str, stat_result]

# checkpoints not explicitly tied to a tournament stage are considered "hidden"
hidden_chkpt = lambda tag: not tag.startswith('stage-')

def db_checkpoint(chkpt_tag: str = None, skip_existing: bool = False) -> str | None:
    """Create checkpoint for the current database.  If chkpt_tag is not specified, then
    "ad hoc" identifier will be created using timestamp (with one second granularity, so
    caller must ensure this is not done in quick succession).  Return pathname of
    checkpoint database file, for reference (or `None` if skipped).
    """
    assert db_is_initialized(), "Database not initialized"
    chkpt_tag = chkpt_tag or f"adhoc-{unixtime()}"
    chkpt_path = db_savepath(chkpt_tag)
    if os.path.exists(chkpt_path):
        if skip_existing:
            log.trace(f"Skipping checkpoint for existing file '{chkpt_path}'")
            return None
        elif cfg.get('strict_checkpoints', False):
            raise FileExistsError(f"Cannot overwrite existing file '{chkpt_path}'")
        log.info(f"Overwriting existing checkpoint file '{chkpt_path}'")
    db.backup_to_file(chkpt_path)
    # NOTE: we are (currently) not writing the NOTICE log message here, since there is
    # more information conveyed if the caller writes it--may want to REVISIT this!
    return chkpt_path

def restore_from_checkpoint(chkpt_tag: str) -> None:
    """Restore current database from checkpoint file (with specified tag).  NOTE: not much
    integrity checking is done (other than pathname similarity), so this operation should
    be used with caution.  As a safeguard, we create a timestamped "hidden" checkpoint
    (with "restr" tag indicator) just before the restoration.
    """
    assert db_is_initialized(), "Database not initialized"
    chkpts = get_checkpoints(include_hidden=True)
    if chkpt_tag not in chkpts:
        raise RuntimeError(f"Invalid checkpoint tag '{chkpt_tag}'")
    if hidden_chkpt(chkpt_tag):
        # don't support this for now, since the workflow is not really specified--we will
        # need to think a little about the use cases for hidden checkpoints
        raise RuntimeError(f"Cannot (currently) restore from hidden checkpoint '{chkpt_tag}'")
    chkpt_path = db_savepath(chkpt_tag)
    if not os.path.exists(chkpt_path):
        raise FileExistsError(f"Checkpoint file '{chkpt_path}' does not exist")

    ts = unixtime()
    hidden_file = db_checkpoint(f"restr-{ts}")
    log.notice(f"Database checkpoint written to '{hidden_file}'")
    db_close()

    chkpt_db = CySqliteDatabase(chkpt_path, pragmas=pragmas, **db_params)
    chkpt_db.backup(db)  # ...actually "restore" (going in this direction)
    chkpt_db.close()
    log.notice(f"Database restored from checkpoint file '{chkpt_path}'")

    # now archive all pre-existing checkpoint files newer than the one we just restored
    # from, since they are essentially now rendered obsolete (or at least, will be, upon
    # the first new update)
    chkpt_ctime = stat(chkpt_path).st_ctime
    to_archive = {t: info for t, info in chkpts.items() if info.st_ctime > chkpt_ctime}
    archive_dir = archive_checkpoints(str(ts), to_archive)
    shutil.move(hidden_file, archive_dir)
    log.debug(f"archiving file '{hidden_file}' to dir '{archive_dir}'")

def archive_checkpoints(archive_tag: str, chkpts: ChkptSeq = None) -> str | None:
    """Archive specified (or all) checkpoint files for the current database.  Return
    pathname of the archive directory (or `None` if no checkpoints to archive).
    """
    chkpts = chkpts or get_checkpoints(include_hidden=True)
    if not chkpts:
        log.info(f"No checkpoints to archive for tag '{archive_tag}'")
        return None
    archive_dir = os.path.join(DATA_DIR, f"archive-{archive_tag}")
    log.info(f"Archiving {len(chkpts)} checkpoints to '{archive_dir}'")
    makedirs(archive_dir, exist_ok=True)
    for chkpt_tag in chkpts:
        filepath = db_savepath(chkpt_tag)
        shutil.move(filepath, archive_dir)
        log.debug(f"archiving file '{filepath}' to dir '{archive_dir}'")
    return archive_dir

filesize = lambda tag, info: f"File size (bytes): {info.st_size}"

def get_checkpoints(include_hidden: bool = False, do_print: bool = False,
                    chkpt_desc: Callable = filesize) -> ChkptSeq:
    """Get dict of checkpoints (indexed by tag, with file info from `stat` as the value)
    for the current database, in ascending chronological order.  "Hidden" checkpoints (if
    requested) include those implicitly generated before database restores, or otherwise
    created ad hoc.
    """
    assert db_is_initialized(), "Database not initialized"
    pfx = db_name() + '-'
    pattern = pfx + '*' + DB_SAVETYPE
    get_tag = lambda fn: fn.removeprefix(pfx).removesuffix(DB_SAVETYPE)
    files = glob(pattern, root_dir=DATA_DIR)
    # represented as: list[tuple[tag, stat_result]]
    chkpts = [(get_tag(f), stat(os.path.join(DATA_DIR, f))) for f in files
              if include_hidden or not hidden_chkpt(get_tag(f))]
    chkpt_seq = dict(sorted(chkpts, key=lambda cp: cp[1].st_ctime))
    if do_print:
        print(f"{'Checkpoint Tag':18}\t{'Timestamp':28}\tDescription")
        print(f"{'-' * 16:18}\t{'-' * 26:28}\t{'-' * 25}")
        for tag, info in chkpt_seq.items():
            ctime = datetime.fromtimestamp(info.st_ctime)
            print(f"{tag:18}\t{str(ctime):28}\t{chkpt_desc(tag, info)}")
    return chkpt_seq

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
