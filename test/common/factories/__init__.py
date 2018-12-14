# -*- coding: utf-8 -*-

"""Factory classes for easily generating test objects."""
from __future__ import unicode_literals

from .base import set_session

from .annotation import Annotation
from .document import Document, DocumentMeta, DocumentURI
from .group import Group, OpenGroup, RestrictedGroup
from .organization import Organization
from .user import User
from .user_identity import UserIdentity

__all__ = (
    "Annotation",
    "Document",
    "DocumentMeta",
    "DocumentURI",
    "Group",
    "OpenGroup",
    "Organization",
    "RestrictedGroup",
    "User",
    "UserIdentity",
    "set_session",
)
