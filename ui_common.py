# -*- coding: utf-8 -*-

"""Common renderers and utility calls for all UI layers (data, admin, mobile, server).
"""

from collections.abc import Callable
from http import HTTPStatus
import re

from flask import g, request, render_template, redirect as flask_redirect, abort

from core import log, DataError

#################
# utility stuff #
#################

# NOTE: more utility stuff at the bottom of this file

MOBILE_REGEX = r'Mobile|Android|iPhone'

def is_mobile() -> bool:
    """Determine mobile client by the user-agent string
    """
    return re.search(MOBILE_REGEX, request.user_agent.string) is not None

#############
# renderers #
#############

def ajax_data(data: dict | list | str) -> dict:
    """Wrapper for returning specified data in the structure expected by DataTables for an
    ajax data source.  `data` must be specified.
    """
    return ajax_response(True, data=data)

def ajax_succ(info_msg: str = None, data: dict | list | str = None) -> dict:
    """Convenience function (slightly shorter).  `info_msg` is optional.
    """
    return ajax_response(True, msg=info_msg, data=data)

def ajax_error(err_msg: str, data: dict | list | str = None) -> dict:
    """Convenience function (slightly shorter).  `err_msg` must be specified.
    """
    return ajax_response(False, msg=err_msg, data=data)

def ajax_response(succ: bool, msg: str = None, data: dict | list | str = None) -> dict:
    """Encapsulate response to an ajax request (GET or POST).  Note that clients can check
    either the `succ` or `err` field to determine the result.  The return `data` is passed
    through to the front-end, with the format being context-dependent (e.g. dict or list
    representing JSON data, or a string directive understood by the client side).

    LATER: we may want to add UI selectors as additional return elements, indicating rows
    and/or cells to highlight, set focus, etc.!!!
    """
    assert succ or msg, "`msg` arg is required for errors"
    if msg and g.api_call:
        msg = msg.replace("<br>", "\n")
    return {
        'succ'   : succ,
        'err'    : None if succ else msg,
        'info'   : msg if succ else None,
        'data'   : data
    }

# API context mapper processes a context dict before jsonification
ApiCtxMapper = Callable[[dict], dict]

def render_response(render_fmt: str | tuple[str, ApiCtxMapper], **ctx) -> str:
    """Either render an app template or formulate an ajax json response, depending on the
    `g.api_call` flag, using the specified context information.  The first argument is
    either a Jinja template name (in which case no context remapping is done for API
    calls), or a tuple of (tmpl_name, ctx_mapper).
    """
    if isinstance(render_fmt, tuple):
        assert len(render_fmt) == 2
        tmpl_name, ctx_mapper = render_fmt
    else:
        assert isinstance(render_fmt, str)
        tmpl_name, ctx_mapper = render_fmt, None
    if g.api_call:
        err_msg = ctx.pop('err_msg', None)
        if err_msg:
            return ajax_error(err_msg, ctx)
        return ajax_data(ctx_mapper(ctx) if ctx_mapper else ctx)
    return render_template(tmpl_name, **ctx)
    
def redirect(location: str) -> str:
    """Wrapper around `flask.redirect` to properly handle both app and API calls.
    """
    if g.api_call:
        # TODO: don't do redirects for API calls, just check for flashed messages and
        # incorporate them in the response, along with intended (suggested?) location
        # information--need to complete this!!!
        data = {'redirect': location}
        return ajax_data(data)
    return flask_redirect(location)

def render_error(code: int, name: str = None, desc: str = None) -> str:
    """Mobile-adjusted error page (replacement for `flask.abort`).
    """
    if not is_mobile:
        abort(code, description=desc)

    err = HTTPStatus(code)
    context = {
        'title'      : f"{code} {err._name_}",
        'error'      : name or err.phrase,
        'description': desc or err.description
    }
    return render_template(ERROR_TEMPLATE, **context), code
