#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from os import stat_result

from schema import StageData

from database import get_checkpoints

STR_MAP = {
    'restr': "Pre-restore",
    'adhoc': "Ad hoc"
}

def chkpt_desc(tag: str, info: stat_result) -> str:
    """Return human-readable description for checkpoint tag (with file info).
    """
    parts = tag.split('-')
    if len(parts) == 2:
        what = STR_MAP.get(parts[0], parts[0])
        when = datetime.fromtimestamp(int(parts[1]))
        return f"{what} ({str(when)})"

    assert parts[0] == 'stage'
    assert parts[2] in ('activ', 'compl')
    stage = int(parts[1])
    compl = parts[2] == 'compl'
    rnd_str = f" (round {parts[3]})" if len(parts) == 4 else ""
    stage_data = StageData[stage]
    return (stage_data.compl_msg if compl else stage_data.start_msg) + rnd_str

def list_checkpoints(include_hidden: bool = False) -> None:
    """
    """
    chkpt_seq = get_checkpoints(include_hidden=include_hidden)
    print(f"{'Checkpoint Tag':18}\t{'Timestamp':28}\tDescription")
    print(f"{'-' * 16:18}\t{'-' * 26:28}\t{'-' * 25}")
    for tag, info in chkpt_seq.items():
        ctime = datetime.fromtimestamp(info.st_ctime)
        print(f"{tag:18}\t{str(ctime):28}\t{chkpt_desc(tag, info)}")

########
# main #
########

import sys

from ckautils import parse_argv

from database import db_init, db_close, restore_from_checkpoint

DB_UTILS = {
    'list_checkpoints'       : list_checkpoints,
    'restore_from_checkpoint': restore_from_checkpoint
}

def main() -> int:
    """Built-in driver to invoke database functions

    Usage: python -m database <db_name> <func> [<args>]

    Functions (and args):
      - list_checkpoints [include_hidden=<bool>]
      - restore_from_checkpoint <chkpt_tag>
    """
    mod_func = None
    usage = lambda msg: msg + "\n\n" + main.__doc__
    if len(sys.argv) < 2:
        return usage(f"Database name not specified")
    if len(sys.argv) < 3:
        return usage(f"Function not specified")

    db_name = sys.argv[1]
    func_name = sys.argv[2]
    if func_name not in DB_UTILS:
        return usage(f"Unknown function '{func_name}'")
    else:
        mod_func = DB_UTILS[func_name]

    args, kwargs = parse_argv(sys.argv[3:])
    db_init(db_name, force=True)
    mod_func(*args, **kwargs)  # will throw exceptions on error
    db_close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
