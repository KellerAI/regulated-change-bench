from datetime import timedelta

import pytest

from payments import policy, rbac
from payments.routes import ROUTES
from payments.session import Session


@pytest.mark.control(obligation="SES-1", coverage="exhaustive", domain="payments.privileged_idle_minutes")
def test_privileged_idle_timeout_within_policy(policy_params, access_policy, platform):
    approved_minutes = policy_params["payments.privileged_idle_minutes"]
    assert policy.PRIVILEGED_IDLE_MINUTES <= approved_minutes
    limit = timedelta(minutes=approved_minutes)
    start = platform.clock.now()
    for seconds in range(0, 2 * approved_minutes * 60 + 1, 15):
        idle = timedelta(seconds=seconds)
        session = Session("probe", "probe.user", "treasury_manager", True, start)
        if idle >= limit:
            assert not session.is_active(start + idle, privileged=True), idle
    privileged = set(access_policy["privileged"]) | set(rbac.PRIVILEGED)
    for route in ROUTES:
        if route.action not in privileged:
            continue
        allowed = [r for r in access_policy["roles"] if access_policy["matrix"][r].get(route.action)]
        role = allowed[0] if allowed else "clerk"
        token = platform.token(f"probe.{route.action}", role=role, mfa=True)
        platform.clock.advance(minutes=approved_minutes)
        response = platform.client.request(route.method, route.pattern.replace("{id}", "1"), token, {})
        assert response.status == 401, route.key
        assert response.json()["error"] == "session_expired", route.key
