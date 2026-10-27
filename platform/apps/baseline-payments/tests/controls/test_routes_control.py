import pytest

from payments import rbac
from payments.routes import ROUTES


def concrete(pattern: str) -> str:
    return pattern.replace("{id}", "1")


def role_allowed(access_policy, action):
    for role in access_policy["roles"]:
        if access_policy["matrix"][role].get(action):
            return role
    return None


@pytest.mark.control(obligation="MFA-1", coverage="exhaustive", domain="payments.routes")
def test_privileged_routes_require_mfa(access_policy, platform):
    approved_privileged = set(access_policy["privileged"])
    assert set(rbac.PRIVILEGED) == approved_privileged
    privileged = approved_privileged | set(rbac.PRIVILEGED)
    known_actions = set(access_policy["actions"])
    unknown = [route.key for route in ROUTES if route.action is not None and route.action not in known_actions]
    assert unknown == []
    without_mfa = [route.key for route in ROUTES if route.action in privileged and not route.mfa]
    assert without_mfa == []
    for route in ROUTES:
        if route.action not in privileged:
            continue
        role = role_allowed(access_policy, route.action)
        token = platform.token(f"probe.{route.action}", role=role or "clerk", mfa=False)
        response = platform.client.request(route.method, concrete(route.pattern), token, {})
        assert response.status == 403, route.key
        assert response.json()["error"] == "mfa_required", route.key
