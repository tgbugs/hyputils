# -*- coding: utf-8 -*-
"""
A module into which all ORM classes are imported.

To avoid circular imports almost all code should import ORM classes from this
module rather than importing them directly,
``from h import models`` rather than ``from h.foo import models``

This is a convenience - you can just import this one module and all of the
ORM classes will be defined, instead of having to import every models module
individually.

For example when testing ORM classes the test module for ``h.foo.models.Bar``
can't just import ``h.foo.models``, it would also need to import the models
module for each database table that ``Bar`` has a (direct or indirect) foreign
key to. So for convenience the test module can instead just do
``from h import models`` and have all ORM classes be defined.

"""
from __future__ import unicode_literals

from h.models.annotation import Annotation
from h.models.document import Document, DocumentMeta, DocumentURI
from h.models.group import Group
from h.models.organization import Organization
from h.models.user import User
from h.models.user_identity import UserIdentity

__all__ = (
    "Annotation",
    "Document",
    "DocumentMeta",
    "DocumentURI",
    "Group",
    "Organization",
    "User",
    "UserIdentity",
)
