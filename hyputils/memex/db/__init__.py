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

emptyset = """<svg width="400" height="400" version="1.0" xmlns="http://www.w3.org/2000/svg">
<path d="m377.25 39.844-48.828 48.828c27.994 31.739 41.992 68.929 41.992 111.57-3.7e-4 47.038-16.683 87.199-50.049 120.48-33.366 33.285-73.568 49.927-120.61 49.927-42.481-1e-5 -79.671-13.835-111.57-41.504l-48.34 48.096-17.09-17.09 48.584-47.852c-27.995-32.226-41.992-69.58-41.992-112.06-2.9e-5 -47.038 16.642-87.199 49.927-120.48 33.284-33.284 73.445-49.926 120.48-49.927 42.643 3.36e-4 79.834 13.998 111.57 41.992l49.072-49.072 16.846 17.09zm-83.008 48.828c-27.018-23.274-58.513-34.912-94.482-34.912-40.202 3.12e-4 -74.666 14.364-103.39 43.091-28.727 28.727-43.091 63.192-43.091 103.39-5.3e-5 35.97 11.637 67.464 34.912 94.482l206.05-206.05zm52.002 111.57c-3.4e-4 -35.97-11.638-67.464-34.912-94.482l-206.05 206.05c27.018 23.275 58.512 34.912 94.482 34.912 40.202 1e-5 74.666-14.364 103.39-43.091 28.727-28.727 43.09-63.192 43.091-103.39z"/>
</svg>"""


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
    import hyputils.memex.models  # noqa

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
        logo = emptyset
    else:
        with open(logopath, 'rb') as f:
            logo = f.read().decode("utf-8")

    session = Session(bind=engine)

    try:
        default_org = models.Organization.default(session)
    except exc.NoResultFound:
        default_org = None

    if default_org is None:
        default_org = models.Organization(
            name="Hypothesis", authority=authority, pubid="__default__"
        )
        default_org.logo = logo
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
