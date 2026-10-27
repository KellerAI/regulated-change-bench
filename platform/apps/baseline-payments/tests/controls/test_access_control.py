import pytest

from payments import rbac


def all_roles(access_policy):
    return sorted(set(access_policy["roles"]) | set(rbac.ROLES))


def all_actions(access_policy):
    return sorted(set(access_policy["actions"]) | set(rbac.ACTIONS))


@pytest.mark.control(obligation="ACC-1", coverage="exhaustive", domain="payments.roles_x_actions")
def test_matrix_equals_approved_policy(access_policy):
    assert set(rbac.ROLES) == set(access_policy["roles"])
    assert set(rbac.ACTIONS) == set(access_policy["actions"])
    matrix = access_policy["matrix"]
    differences = []
    for role in all_roles(access_policy):
        for action in all_actions(access_policy):
            approved = matrix.get(role, {}).get(action)
            if not isinstance(approved, bool):
                differences.append((role, action, "no approved value"))
            elif rbac.is_allowed(role, action) != approved:
                differences.append((role, action, f"approved={approved}"))
    assert differences == []
    for role, action in rbac.GRANTS:
        assert matrix.get(role, {}).get(action) is True, (role, action)
    assert not rbac.is_allowed("unlisted_role", "view_account")
    for role in all_roles(access_policy):
        assert not rbac.is_allowed(role, "unlisted_action")


@pytest.mark.control(obligation="ACC-2", coverage="exhaustive", domain="payments.actions")
def test_auditor_is_read_only(access_policy):
    approved_state_changing = set(access_policy["state_changing"])
    assert set(rbac.STATE_CHANGING) == approved_state_changing
    state_changing = approved_state_changing | set(rbac.STATE_CHANGING)
    writes = []
    for action in all_actions(access_policy):
        if action in state_changing and rbac.is_allowed("auditor", action):
            writes.append(action)
    assert writes == []


@pytest.mark.control(obligation="SOD-1", coverage="exhaustive", domain="payments.actions")
def test_it_admin_cannot_approve_or_release(access_policy):
    rules = access_policy["segregation_of_duties"]
    assert any(rule["role"] == "it_admin" for rule in rules)
    breaches = []
    for rule in rules:
        assert rule["role"] in rbac.ROLES
        for action in all_actions(access_policy):
            if action in rule["must_not"] and rbac.is_allowed(rule["role"], action):
                breaches.append((rule["role"], action))
    assert breaches == []
