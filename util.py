# -*- coding: utf-8 -*-

"""Low-level utilities (dependent only on `schema` and below), not used in the actual
application processing and/or interfaces.  Direct ORM usage is okay in here.
"""

import csv
import os
import sys

from database import db_init, db_close
from schema import Player, Team

EXCLUDE_FIELDS = {
    'created_at',
    'updated_at'
}

def dump_player_data() -> None:
    """Dump all player data, with created/updated timestamps filtered out (to facilitate
    easier comparison).
    """
    cls = Player
    fields = filter(lambda x: x not in EXCLUDE_FIELDS, cls._meta.sorted_field_names)
    writer = csv.DictWriter(sys.stdout, fieldnames=fields, extrasaction='ignore',
                            dialect='excel', lineterminator=os.linesep)
    writer.writeheader()
    writer.writerows(rec.__data__ for rec in cls.select().order_by(cls.id))

def dump_team_data() -> None:
    """Dump all team data, with created/updated timestamps filtered out (to facilitate
    easier comparison).
    """
    cls = Team
    fields = filter(lambda x: x not in EXCLUDE_FIELDS, cls._meta.sorted_field_names)
    writer = csv.DictWriter(sys.stdout, fieldnames=fields, extrasaction='ignore',
                            dialect='excel', lineterminator=os.linesep)
    writer.writeheader()
    writer.writerows(rec.__data__ for rec in cls.select().order_by(cls.id))

########
# main #
########

MOD_FUNCS = [
    'dump_player_data',
    'dump_team_data'
]

import sys

from ckautils import parse_argv

def main() -> int:
    """Built-in driver to invoke module functions

    Usage: python -m util <tourn_name> <func> [<args> ...]

    Functions/usage:
    """
    if len(sys.argv) < 2:
        print(main.__doc__)
        print(f"Tournament name not specified", file=sys.stderr)
        return -1
    if len(sys.argv) < 3:
        print(main.__doc__)
        print(f"Module function not specified", file=sys.stderr)
        return -1
    elif sys.argv[2] not in MOD_FUNCS:
        print(f"Unknown module function '{sys.argv[2]}'", file=sys.stderr)
        return -1

    tourn_name = sys.argv[1]
    mod_func = globals()[sys.argv[2]]
    args, kwargs = parse_argv(sys.argv[3:])

    db_init(tourn_name, force=True)
    mod_func(*args, **kwargs)  # will throw exceptions on error
    db_close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
