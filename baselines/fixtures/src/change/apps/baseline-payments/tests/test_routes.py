from payments.routes import ROUTES


def test_payment_status_route_is_read_only():
    route = next(r for r in ROUTES if r.path == "/payments/{id}/status")
    assert route.method == "GET"
    assert route.action == "view_account"


def test_route_paths_are_unique():
    keys = [(r.method, r.path) for r in ROUTES]
    assert len(keys) == len(set(keys))
