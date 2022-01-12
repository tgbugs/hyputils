# -*- coding: utf-8 -*-
# pylint: disable=no-self-use
"""
The `conftest` module is automatically loaded by pytest and serves as a place
to put fixture functions that are useful application-wide.
"""
from __future__ import unicode_literals

import functools
import os

from unittest import mock
import pytest

import sqlalchemy
from sqlalchemy.orm import sessionmaker
from webob.multidict import MultiDict

from hyputils.memex import db
from hyputils.memex import models
from hyputils.memex.settings import database_url
from hyputils.memex._compat import text_type

TEST_AUTHORITY = "example.com"
TEST_DATABASE_URL = database_url(
    os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost/htest")
)

Session = sessionmaker()


class DummySession(object):

    """
    A dummy database session.
    """

    def __init__(self):
        self.added = []
        self.deleted = []
        self.flushed = False

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        self.flushed = True


class DummyRequest(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def autopatcher(request, target, **kwargs):
    """Patch and cleanup automatically. Wraps :py:func:`mock.patch`."""
    options = {"autospec": True}
    options.update(kwargs)
    patcher = mock.patch(target, **options)
    obj = patcher.start()
    request.addfinalizer(patcher.stop)
    return obj


@pytest.fixture(scope="session")
def db_engine():
    """Set up the database connection and create tables."""
    engine = sqlalchemy.create_engine(TEST_DATABASE_URL)
    db.init(engine, should_create=True, should_drop=True, authority=TEST_AUTHORITY)
    return engine


@pytest.fixture
def default_organization(db_session):
    return models.Organization.default(db_session)


@pytest.fixture
def db_session(db_engine):
    """
    Prepare the SQLAlchemy session object.

    We enable fast repeatable database tests by setting up the database only
    once per session (see :func:`db_engine`) and then wrapping each test
    function in a transaction that is rolled back.

    Additionally, we set a SAVEPOINT before entering the test, and if we
    detect that the test has committed (i.e. released the savepoint) we
    immediately open another. This has the effect of preventing test code from
    committing the outer transaction.
    """
    conn = db_engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)
    session.begin_nested()

    @sqlalchemy.event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def factories(db_session):
    from ..common import factories

    factories.set_session(db_session)
    yield factories
    factories.set_session(None)


@pytest.fixture
def fake_db_session():
    return DummySession()


@pytest.fixture
def matchers():
    from ..common import matchers

    return matchers


@pytest.fixture
def patch(request):
    return functools.partial(autopatcher, request)


@pytest.fixture
def pyramid_request(db_session):
    """Dummy Pyramid request object."""
    request = DummyRequest(db=db_session)
    request.authenticated_userid = 'THIS IS NOT ACTULLY A USERID LOL'
    request.default_authority = text_type(TEST_AUTHORITY)
    request.create_form = mock.Mock()
    request.matched_route = mock.Mock()
    request.is_xhr = False
    request.params = MultiDict()
    request.GET = request.params
    request.POST = request.params
    request.user = None
    return request
