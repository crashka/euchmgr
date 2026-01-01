# -*- coding: utf-8 -*-

from flask_login import LoginManager, UserMixin, AnonymousUserMixin, current_user

class EuchmgrUser(UserMixin):
    """Augment the flask_login mixin with admin awareness.
    """
    is_admin: bool = False

ANONYMOUS_USER = 'anonymous'

class AnonymousUser(AnonymousUserMixin):
    """Augment the flask_login mixin with name and admin awareness.
    """
    name: str = ANONYMOUS_USER
    is_admin: bool = False
    
ADMIN_USER = 'admin'
ADMIN_ID = -1  # must be distinct from all other user ids!

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

class EuchmgrLogin(LoginManager):
    """Augment flask_login class with our anonymous user representation.
    """
    def __init__(self, app=None, add_context_processor=True):
        super().__init__(app=app, add_context_processor=add_context_processor)
        self.anonymous_user = AnonymousUser
