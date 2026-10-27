import pytest

from payments import rbac
from payments.routes import ROUTES


@pytest.mark.control(obligation="MFA-1", coverage="exhaustive", domain="payments.routes")
def test_privileged_routes_require_mfa():
    for route in ROUTES:
        if route.action in rbac.PRIVILEGED:
            assert route.mfa, route
