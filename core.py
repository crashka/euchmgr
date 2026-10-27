# -*- coding: utf-8 -*-

"""Core module - shared/common resources
"""

from os import makedirs, environ, rename
import os.path
from socket import gethostname
from datetime import datetime
from logging.handlers import RotatingFileHandler

from ckautils import Config, logging, TRACE
from peewee import Proxy

#####################
# files/directories #
#####################

FILE_DIR     = os.path.dirname(os.path.realpath(__file__))
#BASE_DIR     = os.path.realpath(os.path.join(FILE_DIR, os.pardir))
BASE_DIR     = FILE_DIR
CONFIG_DIR   = os.path.join(BASE_DIR, 'config')
DATA_DIR     = os.path.join(BASE_DIR, 'data')
LOG_DIR      = os.path.join(BASE_DIR, 'log')
BRACKETS_DIR = os.path.join(BASE_DIR, 'brackets')
RESOURCE_DIR = os.path.join(BASE_DIR, 'resources')
UPLOAD_DIR   = os.path.join(BASE_DIR, 'uploads')
TEST_DIR     = os.path.join(BASE_DIR, 'tests')

def DataFile(file_name: str, rel_path: str | list[str] = DATA_DIR) -> str:
    """Given name of file, return full path name (in DATA_DIR, or specified list of path
    directories relative to project BASE_DIR)
    """
    if isinstance(rel_path, str):
        rel_path = [rel_path]
    file_dir = os.path.join(BASE_DIR, *rel_path)
    makedirs(file_dir, exist_ok=True)
    return os.path.join(file_dir, file_name)

def BracketsFile(file_name: str) -> str:
    """Convenience wrapper around DataFile
    """
    return DataFile(file_name, BRACKETS_DIR)

def ResourceFile(file_name: str) -> str:
    """Convenience wrapper around DataFile
    """
    return DataFile(file_name, RESOURCE_DIR)

##########
# config #
##########

CONFIG_FILES = ['config.yml']

config = Config(CONFIG_FILES, CONFIG_DIR)
hostname = gethostname()
profile = hostname if hostname in config.profile_data else None

#####################
# debugging/logging #
#####################

DEBUG = int(environ.get('EUCHMGR_DEBUG') or 0)

# create logger (TODO: logging parameters belong in config file as well!!!)
DFLT_LOGGER = 'euchmgr'
LOG_FILE_MAX = 50000000
LOG_FILE_NUM = 50
LOG_FMTR = logging.Formatter('%(asctime)s %(levelname)s [%(filename)s:%(lineno)s]: %(message)s')

LoggerClass = logging.getLoggerClass()

class LoggerProxy(Proxy):
    """Proxy class that allows us to set logger (and thus, log file) on "initialization"
    (which includes *re*-initialization).
    """
    def __init__(self, logger: LoggerClass = None):
        """Initialize with the specified logger (optional).  We know the parent __init__
        doesn't (currently) take any arguments.
        """
        super().__init__()
        if logger:
            self.initialize(logger)

def get_logger(name: str) -> LoggerClass:
    """Create (and return) logger with the specified name.  Log file will be determined by
    the logger name.
    """
    log_file = name + '.log'
    log_path = os.path.join(LOG_DIR, log_file)
    log_hand = RotatingFileHandler(log_path, 'a', LOG_FILE_MAX, LOG_FILE_NUM)
    log_hand.setLevel(TRACE)
    log_hand.setFormatter(LOG_FMTR)

    # `log` here is a local variable
    log = logging.getLogger(name)
    log.setLevel(logging.INFO)
    log.addHandler(log_hand)
    if DEBUG:
        log.setLevel(logging.DEBUG)
        if DEBUG > 1:
            dbg_hand = logging.StreamHandler()
            dbg_hand.setLevel(TRACE)
            dbg_hand.setFormatter(LOG_FMTR)
            log.addHandler(dbg_hand)
            if DEBUG > 2:
                log.setLevel(TRACE)
    return log

def set_logger(name: str) -> bool:
    """Replace current logger in the global proxy object.  Once a non-default logger is
    set, it is considered locked-in and cannot be changed.
    """
    global log
    if name == log.name:
        log.debug(f"Ignoring setting logger '{log.name}' to itself")
        return True
    elif log.name != DFLT_LOGGER:
        log.info(f"Ignoring re-setting non-default logger '{log.name}' to '{name}'")
        return False

    log.initialize(get_logger(name))
    return True

# set default logger on import (logging against an empty proxy would break things)
log = LoggerProxy(get_logger(DFLT_LOGGER))

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
