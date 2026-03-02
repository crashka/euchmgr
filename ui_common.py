# -*- coding: utf-8 -*-

"""Common renderers and utility calls for all UI layers (data, admin, mobile, server).
"""

from collections.abc import Callable
from types import FunctionType, MethodType
from http import HTTPStatus
from dataclasses import asdict
import re

from ckautils import typecast
from flask import (g, request, render_template, redirect as flask_redirect, abort,
                   get_flashed_messages)

from core import log, ImplementationError
from security import SecurityMixin
from database import BaseModel

#################
# utility stuff #
#################

MOBILE_REGEX = r'Mobile|Android|iPhone'

def mobile_client() -> bool:
    """Determine mobile client by the user-agent string.
    """
    return re.search(MOBILE_REGEX, request.user_agent.string) is not None

def is_mobile() -> bool:
    """TEMP: for compatibility (later remove when callers are converted)!!!
    """
    return g.mobile

Scalar = str | int | float | bool | None

def process_flashes() -> tuple[dict[str, Scalar], list[Scalar]]:
    """Process flashed messages, returning a dict of parameterized flashes (i.e. messages
    of the form "key=val"), as well as a list of unparameterized flashes (which are now
    deprecated).  `err` and `info` are special keys for which multiple flashes are allowed
    (returned as lists of scalar values).  Duplicate flashes (with scalar values) for all
    other keys will result in an exception upon processing.

    Note that this call clears out the flashed message buffer for the user session.
    """
    params = {}
    msgs = []
    for msg in get_flashed_messages():
        if m := re.fullmatch(r'(\w+)=(.+)', msg):
            key, val = m.group(1, 2)
            if key in ('err', 'info'):
                if key not in params:
                    params[key] = []
                params[key].append(typecast(val))
            else:
                if key in params:
                    raise LogicError(f"Duplicate param key '{key}'")
                params[key] = typecast(val)
        else:
            msgs.append(msg)

    return params, msgs

def msg_join(msgs: list[str]) -> str:
    """Context-senstive message joiner for `err` and `info` flahsed messages.
    """
    msg_sep = "\n" if g.api_call else "<br>"
    return msg_sep.join(msgs)

# "context mappers" process a context dict before jsonification
CtxMapper = Callable[[dict], dict]

def dflt_ctx_mapper(ctx_in: dict) -> dict:
    """TEMP: quick and dirty version for development!!!
    """
    ctx_out = {}
    for key, val in ctx_in.items():
        if key in ('stage_games', 'partner_picks') and val:
            # TODO: generalize identification of list[BaseModel]!!!
            assert isinstance(val, list)
            assert isinstance(val[0], BaseModel)
            assert hasattr(val[0], '__data__')
            ctx_out[key] = [x.__data__ for x in val]
        elif isinstance(val, (str, int, float, list, tuple, dict)) or val is None:
            # this assumes that sequence/mapping components are json-serializable
            ctx_out[key] = val
        elif isinstance(val, BaseModel):
            assert hasattr(val, '__data__')
            ctx_out[key] = val.__data__
        elif isinstance(val, SecurityMixin):
            assert hasattr(val, 'asdict')
            ctx_out[key] = val.asdict()
        elif isinstance(val, Callable):
            # note that this covers functions as well as classes (including enums, etc.),
            # which are all typically not natively serializable
            log.debug(f"skipping ctx mapping for '{key}' (callable type '{type(val)}')")
            continue
        else:
            log.debug(f"implicit ctx mapping for '{key}' (type '{type(val)}')")
            ctx_out[key] = val

    return ctx_out

#############
# renderers #
#############

ERROR_TEMPLATE = "error.html"

def render_response(render_fmt: str | tuple[str, CtxMapper], **ctx) -> str:
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
        tmpl_name, ctx_mapper = render_fmt, dflt_ctx_mapper
    if g.api_call:
        # admin views are not rendered through the API (TEMP: except for View.TOURN, hence
        # the following grimness--this should be FIXED at some point!!!)
        assert g.mobile or tmpl_name.startswith("tourn")
        err_msg = ctx.pop('err_msg', None)
        info_msg = ctx.pop('info_msg', None)
        if err_msg:
            log.debug(f"render_response for API call, err_msg \"{err_msg}\"")
            return api_error(400, err_msg, info_msg)

        mapped_ctx = ctx_mapper(ctx) if ctx_mapper else ctx
        log.debug(f"render_response for API call")
        return api_succ(info_msg, mapped_ctx)
    return render_template(tmpl_name, **ctx)

def redirect(location: str) -> str:
    """Logical redirect to the appropriate post-action view.  For admin and mobile views,
    this is just a wrapper around `flask.redirect`; for API calls, we return directly, and
    only off the direct location as a suggestion.
    """
    if g.api_call:
        params, msgs = process_flashes()
        err_msgs = params.pop('err', [])
        info_msgs = params.pop('info', []) + msgs
        if params:
            raise ImplementationError(f"unexpected flashed params '{params}'")
        err_msg = msg_join(err_msgs) or None
        info_msg = msg_join(info_msgs) or None
        if err_msg:
            log.debug(f"redirect for API call, err_msg \"{err_msg}\"")
            return api_error(400, err_msg, info_msg)

        # TODO: resolve '/' to active view for both admin and mobile!!!
        data = {'redirect': location}
        log.debug(f"redirect (virtual) for API call")
        return api_succ(info_msg, data)
    return flask_redirect(location)

def render_error(code: int, name: str = None, desc: str = None) -> str:
    """Mobile-adjusted error page (replacement for `flask.abort`).  This mechanism is used
    for errors rendered outside of the application UI framework.
    """
    if not is_mobile():
        abort(code, description=desc)

    err = HTTPStatus(code)
    err_msg = name or err.phrase
    err_desc = desc or err.description

    if g.api_call:
        log.debug(f"render_error for API call, err_msg \"{err_msg}\"")
        return api_error(code, err_msg, err_desc)

    context = {
        'title'      : f"{code} {err._name_}",
        'error'      : err_msg,
        'description': err_desc
    }
    return render_template(ERROR_TEMPLATE, **context), code

# TEMP: create "api" return calls using ajax returns as a model--LATER, we need to unify
# these two layers!!!

def api_succ(info_msg: str = None, data: dict | list | str = None) -> dict:
    """Convenience function (slightly shorter).  `info_msg` is optional.
    """
    return {
        'succ': True,
        'err' : None,
        'info': info_msg,
        'data': data
    }

def api_error(code: int, err_msg: str, err_desc: str = None) -> dict:
    """Convenience function (slightly shorter).  `err_msg` must be specified.
    """
    return {
        'succ': False,
        'err' : err_msg,
        'info': err_desc,
        'data': None
    }, code
