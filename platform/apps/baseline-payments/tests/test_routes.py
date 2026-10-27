import pytest

from payments import rbac
from payments.app import HANDLERS, match
from payments.errors import MethodNotAllowed, NotFound
from payments.routes import ROUTES


def test_route_keys_are_unique():
    keys = [route.key for route in ROUTES]
    assert len(keys) == len(set(keys))


def test_every_route_has_a_handler_and_every_handler_a_route():
    assert {route.key for route in ROUTES} == set(HANDLERS)


def test_route_actions_are_known():
    for route in ROUTES:
        assert route.action is None or route.action in rbac.ACTIONS


def test_match_extracts_the_id():
    route, path_id = match("POST", "/payments/42/approve")
    assert route.action == "approve_payment"
    assert path_id == 42


def test_match_without_id():
    route, path_id = match("GET", "/payments")
    assert route.action == "view_account"
    assert path_id is None


def test_unknown_path_is_not_found():
    with pytest.raises(NotFound):
        match("GET", "/admin")


def test_wrong_method_is_reported():
    with pytest.raises(MethodNotAllowed):
        match("DELETE", "/payments/1")


def test_ids_must_be_numeric():
    with pytest.raises(NotFound):
        match("GET", "/payments/abc")
