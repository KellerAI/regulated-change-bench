import pytest

from payments import rbac
from payments.errors import Forbidden


def test_grants_use_known_roles_and_actions():
    for role, action in rbac.GRANTS:
        assert role in rbac.ROLES
        assert action in rbac.ACTIONS


def test_classifications_use_known_actions():
    assert rbac.STATE_CHANGING <= set(rbac.ACTIONS)
    assert rbac.PRIVILEGED <= set(rbac.ACTIONS)


def test_clerk_can_create_but_not_approve():
    assert rbac.is_allowed("clerk", "create_payment")
    assert not rbac.is_allowed("clerk", "approve_payment")


def test_treasury_manager_releases():
    assert rbac.is_allowed("treasury_manager", "release_payment")


def test_unknown_role_or_action_is_denied():
    assert not rbac.is_allowed("contractor", "view_account")
    assert not rbac.is_allowed("clerk", "delete_everything")


def test_require_raises_forbidden():
    rbac.require("auditor", "view_audit")
    with pytest.raises(Forbidden):
        rbac.require("auditor", "release_payment")
