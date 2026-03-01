# -*- coding: utf-8 -*-

"""Test admin UI.
"""
import re

import pytest
from flask import session
from bs4 import BeautifulSoup

from conftest import get_user_client
from test_basic import ROSTER_FILE
from admin import SEL_NEW

def test_index(admin_client):
    """Starting with a cleared session, GET on '/' should return admin login page.
    """
    client = admin_client
    with client.session_transaction() as session:
        session.clear()
    resp = client.get('/', follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/login'

    soup = BeautifulSoup(resp.text, 'html.parser')
    assert soup.find('form', action="/login")

    form = soup.find('form', action="/login")
    assert form.find('select', attrs={'name': "username"})
    assert form.find('input', attrs={'name': "password"})
    select = form.find('select', attrs={'name': "username"})
    assert select.find('option', value="admin")
    option = select.find('option', value="admin")
    assert option.get_text() == 'admin'

def test_login(admin_client):
    """Logging in as admin should return tournament selection view.
    """
    client = admin_client
    data = {'username': "admin", 'password': "119baystate"}
    resp = client.post("/login", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 2
    assert resp.request.path == '/tourn'

    soup = BeautifulSoup(resp.text, 'html.parser')
    assert soup.find('form', action="/tourn/select_tourn")
    assert not soup.find('section', class_="tourn")

    form = soup.find('form', action="/tourn/select_tourn")
    assert form.find('select', attrs={'name': "tourn"})
    select = form.find('select', attrs={'name': "tourn"})
    assert select.find('option', value=SEL_NEW)
    option = select.find('option', value=SEL_NEW)
    assert option.get_text() == SEL_NEW

def test_create_new(admin_client):
    """Selecting "(create new)" should return create tournament view.
    """
    client = admin_client
    data = {'action': "select_tourn", 'tourn': SEL_NEW}
    resp = client.post("/tourn/select_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/tourn'

    soup = BeautifulSoup(resp.text, 'html.parser')
    assert soup.find('form', action="/tourn/select_tourn")
    assert soup.find('form', action="/tourn")
    assert soup.find('section', class_="tourn")

    form = soup.find('form', action="/tourn/select_tourn")
    assert form.find('select', attrs={'name': "tourn"})
    select = form.find('select', attrs={'name': "tourn"})
    assert select.find('option', value='(create new)', selected=True)

    form = soup.find('form', action="/tourn")
    assert form.find('input', attrs={'name': "tourn_id"})
    assert form.find('input', attrs={'name': "tourn_name"})
    assert form.find('input', attrs={'name': "roster_file"})
    assert form.find('input', attrs={'name': "overwrite"})
    assert form.find('button', value="create_tourn", disabled=False)

def test_create_tourn_exists(admin_client):
    """Creating a new tournament should return the Players view.
    """
    client = admin_client
    data = {
        'action'     : "create_tourn",
        'tourn_id'   : "",
        'tourn_name' : "test",
        'roster_file': open(ROSTER_FILE, "rb"),
        'overwrite'  : ""
    }
    resp = client.post("/tourn/create_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 0
    assert resp.request.path == '/tourn/create_tourn'
    err_msg = "show_error(\'Tournament \"test\" already exists"
    assert resp.text.find(err_msg) > -1

def test_create_tourn(admin_client):
    """Creating a new tournament should return the Players view.
    """
    client = admin_client
    data = {
        'action'     : "create_tourn",
        'tourn_id'   : "",
        'tourn_name' : "test",
        'roster_file': open(ROSTER_FILE, "rb"),
        'overwrite'  : "yes"
    }
    resp = client.post("/tourn/create_tourn", data=data, follow_redirects=True)
    assert resp.status_code == 200
    assert len(resp.history) == 1
    assert resp.request.path == '/players'

    soup = BeautifulSoup(resp.text, 'html.parser')
    pass
