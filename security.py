# -*- coding: utf-8 -*-

import os.path
import os

from flask_login import (LoginManager, UserMixin, AnonymousUserMixin, current_user,
                         login_user, logout_user)
from werkzeug.security import generate_password_hash, check_password_hash

from core import DataFile, log

##############
# exceptions #
##############

class AuthenticationError(RuntimeError):
    """Used to distinguish between authentication errors and other login failures
    (e.g. due to configuration, server state, etc.), which are represented by
    `RuntimeError`.
    """
    pass

#####################
# Flask-Login stuff #
#####################

DUMMY_PW_STR = '[dummy pw str]'

class EuchmgrUser(UserMixin):
    """Augment the flask_login mixin with admin awareness.
    """
    is_admin: bool = False

    def login(self, password: str) -> bool:
        """Log the user in using the specified password (only for the web application).
        Return `True` if actual login action was taken, otherwise `False` (e.g. already
        logged in).  Raise `AuthenticationError` for bad password, or `RuntimeError` for
        other login failures (e.g. due to server configuration, status, etc.).

        This call (coupled with `logout`) takes care of all appropriate interactions with
        the underlying Flask-Login extension
        """
        raise NotImplementedError("Needs to be implemented by subclass")

    def logout(self) -> bool:
        """Log the user out (only for the web application).  Return `True` if the actual
        logout action was taken, otherwise `False` (e.g. not previously logged in).

        This call (coupled with `login`) takes care of all appropriate interactions with
        the underlying Flask-Login extension.
        """
        raise NotImplementedError("Needs to be implemented by subclass")

    def setpass(self, password: str) -> None:
        """Set password for user.  Raises exception (with reason) on failure.  Note that
        requirements, policies, etc. are specified by the subclass.
        """
        raise NotImplementedError("Needs to be implemented by subclass")

ANONYMOUS_USER = 'anonymous'

class AnonymousUser(AnonymousUserMixin):
    """Augment the flask_login mixin with name and admin awareness.
    """
    name: str = ANONYMOUS_USER
    is_admin: bool = False

ADMIN_USER    = 'admin'
ADMIN_ID      = -1  # must be distinct from all other user ids!
ADMIN_PW_FILE = 'admin.pw_hash'

class AdminUser(EuchmgrUser):
    """Simplest possible representation of an admin user (should be a singleton, though
    multiple instantiations will be identical).
    """
    id: int = ADMIN_ID
    name: str  = ADMIN_USER
    is_admin: bool = True

    def get_id(self) -> str:
        """Return ID as a string per the flask_login spec, even though the framework
        sometimes access the `id` field directly.  The caller has to be able to handle
        either representation.
        """
        return str(self.id)

    def login(self, password: str) -> bool:
        """See base class.

        Note that we are currently logging passwords for failed logins, to get visibility
        into attempted exploits by hackers.  We will probably remove this later.  The
        current admin password should never appear in the clear.
        """
        pw_file = DataFile(ADMIN_PW_FILE)
        if not os.path.exists(pw_file):
            log.info(f"login denied ({self.name}): pw_file '{pw_file}' does not exist")
            raise RuntimeError("System configuration error")

        if not isinstance(password, str):
            log.info(f"login denied ({self.name}): invalid pw type {type(password)} "
                     f"('{password}')")
            raise AuthenticationError("Bad password specified")

        with open(pw_file, 'r') as f:
            pw_hash = f.read()
        if not check_password_hash(pw_hash, password):
            log.info(f"login failed ({self.name}): bad password ('{password}')")
            raise AuthenticationError("Bad password specified")

        login_user(self)
        log.info(f"login successful ({self.name})")
        return True

    def logout(self) -> bool:
        """See base class.
        """
        assert current_user == self
        logout_user()

    def setpass(self, password: str) -> None:
        """See base class.  Admin logins are disabled if `password` is specified as
        `None`.
        """
        # TODO: enforce password policy (length, diversity, etc.) here!!!
        pw_file = DataFile(ADMIN_PW_FILE)
        file_exists = os.path.exists(pw_file)
        if password is None:
            if file_exists:
                os.remove(pw_file)
                log.info(f"admin pw_file '{pw_file}' removed")
                return
            else:
                log.info(f"admin pw_file '{pw_file}' does not exist")
                return

        with open(pw_file, 'w') as f:
            f.write(generate_password_hash(password))
        written = "overwritten" if file_exists else "written"
        log.info(f"pw_file '{pw_file}' {written}")

class EuchmgrLogin(LoginManager):
    """Augment flask_login class with our anonymous user representation.
    """
    def __init__(self, app=None, add_context_processor=True):
        super().__init__(app=app, add_context_processor=add_context_processor)
        self.anonymous_user = AnonymousUser

########
# main #
########

import sys

from ckautils import parse_argv

def main() -> int:
    """Built-in driver to invoke security functons

    Usage: python -m security <user> <func> [<args>]

    Functions (and args):
      - setpass <password>
    """
    usage = lambda x: x + "\n\n" + main.__doc__
    if len(sys.argv) < 2:
        return usage(f"User not specified")
    if len(sys.argv) < 3:
        return usage(f"Function not specified")

    user_name = sys.argv[1]
    func_name = sys.argv[2]
    args, kwargs = parse_argv(sys.argv[3:])

    if user_name != ADMIN_USER:
        return usage("Only operations against user 'admin' currently supported")
    user = AdminUser()
    func = getattr(user, func_name, None)
    if not func:
        return usage(f"Function '{func_name}' not recognized")
    func(*args, **kwargs)  # will throw exceptions on error
    return 0

if __name__ == '__main__':
    sys.exit(main())
