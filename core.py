# -*- coding: utf-8 -*-

"""Core module - shared/common resources
"""

from os import makedirs, environ, rename
import os.path
from datetime import datetime
import logging
import logging.handlers

#####################
# files/directories #
#####################

FILE_DIR = os.path.dirname(os.path.realpath(__file__))
#BASE_DIR = os.path.realpath(os.path.join(FILE_DIR, os.pardir))
BASE_DIR = FILE_DIR
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR  = os.path.join(BASE_DIR, 'log')

def DataFile(file_name: str, rel_path: str | list[str] = DATA_DIR) -> str:
    """Given name of file, return full path name (in DATA_DIR, or specified list of path
    directories relative to project BASE_DIR)
    """
    if isinstance(rel_path, str):
        rel_path = [rel_path]
    file_dir = os.path.join(BASE_DIR, *rel_path)
    makedirs(file_dir, exist_ok=True)
    return os.path.join(file_dir, file_name)

#####################
# debugging/logging #
#####################

DEBUG = int(environ.get('EUCHMGR_DEBUG') or 0)

# create logger (TODO: logging parameters belong in config file as well!!!)
LOGGER_NAME  = 'euch'
LOG_FILE     = LOGGER_NAME + '.log'
LOG_PATH     = os.path.join(LOG_DIR, LOG_FILE)
LOG_FMTR     = logging.Formatter('%(asctime)s %(levelname)s [%(filename)s:%(lineno)s]: %(message)s')
LOG_FILE_MAX = 50000000
LOG_FILE_NUM = 50

dflt_hand = logging.handlers.RotatingFileHandler(LOG_PATH, 'a', LOG_FILE_MAX, LOG_FILE_NUM)
dflt_hand.setLevel(logging.DEBUG)
dflt_hand.setFormatter(LOG_FMTR)

dbg_hand = logging.StreamHandler()
dbg_hand.setLevel(logging.DEBUG)
dbg_hand.setFormatter(LOG_FMTR)

log = logging.getLogger(LOGGER_NAME)
log.setLevel(logging.INFO)
log.addHandler(dflt_hand)
if DEBUG:
    log.setLevel(logging.DEBUG)
    if DEBUG > 1:
        log.addHandler(dbg_hand)

##############
# exceptions #
##############

class DataError(RuntimeError):
    """Thrown if there is a problem detected with any of the data at runtime, whether due
    to bad and/or insufficient external data or errrant internal data processing
    """
    pass

class ConfigError(RuntimeError):
    """Thrown if there is a problem with a config file entry, or combination of entries
    """
    pass

class LogicError(RuntimeError):
    """Basically the same as an assert, but with a `raise` interface
    """
    pass

class ImplementationError(RuntimeError):
    """Thrown if there is a problem implementing an internal interface (e.g.  `Parser`
    subclass)
    """
    pass
