# -*- coding: utf-8 -*-

"""
Configure and expose the application database session.

This module is responsible for setting up the database session and engine, and
making that accessible to other parts of the application.

Models should inherit from `h.db.Base` in order to have their metadata bound at
application startup.

Most application code should access the database session using the request
property `request.db` which is provided by this module.
"""
from __future__ import unicode_literals

import logging

import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import exc
from sqlalchemy.orm import sessionmaker

__all__ = ("Base", "Session", "init", "make_engine")

log = logging.getLogger(__name__)

# Create a default metadata object with naming conventions for indexes and
# constraints. This makes changing such constraints and indexes with alembic
# after creation much easier. See:
#
#   http://docs.sqlalchemy.org/en/latest/core/constraints.html#configuring-constraint-naming-conventions
#
metadata = sqlalchemy.MetaData(
    naming_convention={
        "ix": "ix__%(column_0_label)s",
        "uq": "uq__%(table_name)s__%(column_0_name)s",
        "ck": "ck__%(table_name)s__%(constraint_name)s",
        "fk": "fk__%(table_name)s__%(column_0_name)s__%(referred_table_name)s",
        "pk": "pk__%(table_name)s",
    }
)

Base = declarative_base(metadata=metadata)

Session = sessionmaker()


def init(engine, base=Base, should_create=False, should_drop=False, authority=None):
    """Initialise the database tables managed by `h.db`."""
    # Import models package to populate the metadata
    import h.models  # noqa

    if should_drop:
        base.metadata.reflect(engine)
        base.metadata.drop_all(engine)
    if should_create:
        # In order to be able to generate UUIDs, we load the uuid-ossp
        # extension.
        engine.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        base.metadata.create_all(engine)

    default_org = _maybe_create_default_organization(engine, authority)
    _maybe_create_world_group(engine, authority, default_org)


def make_engine(settings):
    """Construct a sqlalchemy engine from the passed ``settings``."""
    return sqlalchemy.create_engine(settings["sqlalchemy.url"])


def _maybe_create_default_organization(engine, authority, logopath=None):
    from hyputils.memex import models
    if logopath is None:
        from os.path import dirname
        workingdir = dirname(dirname(dirname(__file__)))
        logopath = workingdir + '/' + 'h/static/images/icons/logo.svg'

    session = Session(bind=engine)

    try:
        default_org = models.Organization.default(session)
    except exc.NoResultFound:
        default_org = None

    if default_org is None:
        default_org = models.Organization(
            name="Hypothesis", authority=authority, pubid="__default__"
        )
        with open(logopath, 'rb') as h_logo:
            default_org.logo = h_logo.read().decode("utf-8")
        session.add(default_org)

    session.commit()
    session.close()

    return default_org


def _maybe_create_world_group(engine, authority, default_org):
    from hyputils.memex import models
    from hyputils.memex.models.group import ReadableBy, WriteableBy

    session = Session(bind=engine)
    world_group = session.query(models.Group).filter_by(pubid="__world__").one_or_none()
    if world_group is None:
        world_group = models.Group(
            name="Public",
            authority=authority,
            joinable_by=None,
            readable_by=ReadableBy.world,
            writeable_by=WriteableBy.authority,
            organization=default_org,
        )
        world_group.pubid = "__world__"
        session.add(world_group)

    session.commit()
    session.close()
