# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from hyputils.memex._compat import PY2
import enum
from unittest.mock import Mock
import pytest

from hyputils.memex.schemas import ValidationError
from hyputils.memex.schemas.base import JSONSchema


class ExampleJSONSchema(JSONSchema):
    # Use `bytes` for property names in Py 2 so that exception messages about
    # missing properties have the same content in Py 2 + Py 3.
    prop_name_type = bytes if PY2 else str

    schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "properties": {
            prop_name_type("foo"): {"type": "string"},
            prop_name_type("bar"): {"type": "integer"},
        },
        "required": [prop_name_type("foo"), prop_name_type("bar")],
    }


class TestJSONSchema(object):
    def test_it_returns_data_when_valid(self):
        data = {"foo": "baz", "bar": 123}

        assert ExampleJSONSchema().validate(data) == data

    def test_it_raises_when_data_invalid(self):
        data = 123  # not an object

        with pytest.raises(ValidationError):
            ExampleJSONSchema().validate(data)

    def test_it_sets_appropriate_error_message_when_data_invalid(self):
        data = {"foo": "baz"}  # required bar is missing

        with pytest.raises(ValidationError) as e:
            ExampleJSONSchema().validate(data)

        message = str(e.value)
        assert message.startswith("'bar' is a required property")

    def test_it_returns_all_errors_in_message(self):
        data = {}  # missing both required fields

        with pytest.raises(ValidationError) as e:
            ExampleJSONSchema().validate(data)

        message = str(e.value)
        assert message.startswith(
            "'foo' is a required property, 'bar' is a required property"
        )
