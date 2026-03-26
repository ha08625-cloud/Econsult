"""
Unit tests for delivery_events.

Confirms the module exports exactly the four expected event constants
with the correct string values, and that it has no application-module
dependencies.
"""

import ast
import importlib
import inspect
import os


def test_event_constants_exist_and_have_correct_values():
    from app.services.delivery_events import (
        DELIVERY_SENT,
        DELIVERY_FAILED,
        DELIVERY_EXHAUSTED,
        DELIVERY_RETRY_TOO_EARLY,
    )

    assert DELIVERY_SENT == "delivery_sent"
    assert DELIVERY_FAILED == "delivery_failed"
    assert DELIVERY_EXHAUSTED == "delivery_exhausted"
    assert DELIVERY_RETRY_TOO_EARLY == "delivery_retry_too_early"


def test_all_constants_are_unique():
    from app.services import delivery_events

    values = [
        delivery_events.DELIVERY_SENT,
        delivery_events.DELIVERY_FAILED,
        delivery_events.DELIVERY_EXHAUSTED,
        delivery_events.DELIVERY_RETRY_TOO_EARLY,
    ]
    assert len(values) == len(set(values)), "Event constants must be unique"


def test_no_application_imports():
    """delivery_events must have no imports from app.*"""
    from app.services import delivery_events

    source_path = inspect.getfile(delivery_events)
    with open(source_path) as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("app."), (
                    f"delivery_events must not import {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("app."):
                raise AssertionError(
                    f"delivery_events must not import from {node.module}"
                )