#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Script to run through entire sequence of euchmgr tournament stages, used for profiling
"""
from os import environ
import sys

from ckautils import parse_argv

from database import db_init, db_close
from schema import Bracket
import euchmgr

########
# main #
########

PROFILE = int(environ.get('EUCHMGR_PROFILE') or 0)
PROF_INTERVAL = 0.0005
if PROFILE:
    from pyinstrument import Profiler
    profiler = Profiler(interval=PROF_INTERVAL)

EXCLUDE_FUNCS = [
    'validate_playoffs',
    'compute_playoff_ranks'
]

ALL_FUNCS = list(filter(lambda x: x not in EXCLUDE_FUNCS, euchmgr.MOD_FUNCS))

def get_func_args(func: str, tourn_name: str) -> dict:
    """Return dict representing arguments to pass into ``func``
    """
    func_args = {
        'tourn_create'         : {'force': True},
        'upload_roster'        : {'csv_path': f"{tourn_name}_roster.csv"},
        'validate_seed_round'  : {'finalize': True},
        'compute_player_ranks' : {'finalize': True},
        'validate_tourn'       : {'finalize': True},
        'compute_team_ranks'   : {'finalize': True},
        'build_playoff_bracket': {'bracket': Bracket.SEMIS}
    }

    if func not in func_args:
        return {}
    return func_args[func]

def main() -> int:
    """Built-in driver to invoke module functions

    Usage: python -m run_auto <tourn_name> <func_list> [<addl_args>]

    where ``func_list`` is a comma-separated list of functions to run, or ``'all'``

    Functions:
      - tourn_create
      - upload_roster
      - generate_player_nums
      - build_seed_bracket
      - fake_seed_games
      - tabulate_seed_round
      - compute_player_ranks
      - prepick_champ_partners
      - fake_pick_partners
      - build_tourn_teams
      - compute_team_seeds
      - build_tourn_bracket
      - fake_tourn_games
      - tabulate_tourn
      - compute_team_ranks
      - build_playoff_bracket
      - validate_playoffs
      - compute_playoff_ranks

    Note that a roster file of ``<tourn_name>_roster.csv`` will be used by default, and
    ``addl_args`` represents keyword args that will be passed into the specified function
    (must be a single function, in this case).
    """
    usage = lambda x: x + "\n\n" + main.__doc__
    if len(sys.argv) < 2:
        return usage("Tournament name not specified")
    if len(sys.argv) < 3:
        return usage("Euchmgr function(s) not specified")

    tourn_name = sys.argv[1]
    func_list = sys.argv[2]
    if func_list == 'all':
        funcs = ALL_FUNCS
    else:
        funcs = func_list.split(',')
        for func in funcs:
            if func not in ALL_FUNCS:
                return usage(f"Unknown function '{func}'")

    args, kwargs = parse_argv(sys.argv[3:])  # pick up additional args
    if args:
        return usage("Unknown args: " + ' '.join(args))
    if kwargs and len(funcs) > 1:
        return usage("Extra args only supported if a single function is specified")
    db_init(tourn_name, force=True)
    if PROFILE:
        profiler.start()
    for func in funcs:
        func_call = getattr(euchmgr, func)
        func_args = get_func_args(func, tourn_name)
        func_call(**(func_args | kwargs))  # will throw exceptions on error
    if PROFILE:
        profiler.stop()
        profiler.print()
        profiler.open_in_browser()
    db_close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
