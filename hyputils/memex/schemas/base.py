# -*- coding: utf-8 -*-

"""Shared functionality for schemas."""

from __future__ import unicode_literals

import copy

import jsonschema


class ValidationError(Exception):
    pass


class JSONSchema(object):
    """
    Validate data according to a Draft 4 JSON Schema.

    Inherit from this class and override the `schema` class property with a
    valid JSON schema.
    """

    schema = {}

    def __init__(self):
        format_checker = jsonschema.FormatChecker()
        self.validator = jsonschema.Draft4Validator(
            self.schema, format_checker=format_checker
        )

    def validate(self, data):
        """
        Validate `data` according to the current schema.

        :param data: The data to be validated
        :returns: valid data
        :raises ~h.schemas.ValidationError: if the data is invalid
        """
        # Take a copy to ensure we don't modify what we were passed.
        appstruct = copy.deepcopy(data)

        errors = list(self.validator.iter_errors(appstruct))
        if errors:
            msg = ", ".join([_format_jsonschema_error(e) for e in errors])
            raise ValidationError(msg)
        return appstruct


def _format_jsonschema_error(error):
    """Format a :py:class:`jsonschema.ValidationError` as a string."""
    if error.path:
        dotted_path = ".".join([str(c) for c in error.path])
        return "{path}: {message}".format(path=dotted_path, message=error.message)
    return error.message
