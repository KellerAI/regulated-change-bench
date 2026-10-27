import json
from pathlib import Path

import pytest

from payments import rbac

POLICY = Path(__file__).resolve().parents[4] / "controls" / "access-policy.json"


@pytest.mark.control(obligation="ACC-1", coverage="exhaustive", domain="payments.roles_x_actions")
def test_matrix_equals_approved_policy():
    approved = {tuple(g) for g in json.loads(POLICY.read_text())["payments"]["grants"]}
    for role in rbac.ROLES:
        for action in rbac.ACTIONS:
            assert rbac.is_allowed(role, action) == ((role, action) in approved), (role, action)
