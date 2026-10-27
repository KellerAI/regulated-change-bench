from support import CORE_BANKING


def add_payee(client, login):
    body = {
        "holder_name": "Northwind Office Supply",
        "category": "vendor",
        "account_number": "880012345678",
        "routing_number": "990000123",
        "tax_id": "00-1234567",
    }
    response = client.post("/payees", login("officer.ben"), body)
    assert response.status == 201
    return response.json()["id"]


def test_health_needs_no_session(client):
    response = client.get("/health")
    assert response.status == 200
    assert response.json() == {"status": "ok"}


def test_missing_or_unknown_token(client):
    assert client.get("/payments").status == 401
    assert client.get("/payments", "not-a-token").status == 401


def test_unknown_route_and_method(client, login):
    assert client.get("/admin", login("clerk.ana")).status == 404
    assert client.request("DELETE", "/payments/1", login("clerk.ana")).status == 405


def test_mfa_is_required_for_approval(client, login):
    response = client.post("/payments/1/approve", login("officer.ben", mfa=False))
    assert response.status == 403
    assert response.json()["error"] == "mfa_required"


def test_role_without_grant_is_forbidden(client, login):
    response = client.get("/audit/events", login("clerk.ana"))
    assert response.status == 403
    assert response.json()["error"] == "forbidden"


def test_payment_flow_over_http(client, login, transport):
    payee_id = add_payee(client, login)
    created = client.post("/payments", login("clerk.ana"), {"payee_id": payee_id, "amount": "12000.00"})
    assert created.status == 201
    payment_id = created.json()["id"]
    assert client.post(f"/payments/{payment_id}/approve", login("officer.ben")).json()["status"] == "pending"
    assert client.post(f"/payments/{payment_id}/approve", login("treasury.eli")).json()["status"] == "approved"
    released = client.post(f"/payments/{payment_id}/release", login("treasury.dee"))
    assert released.status == 200
    assert released.json()["instruction_id"] == "INS-00000001"
    assert len(transport.sent_to(CORE_BANKING)) == 1


def test_self_approval_over_http(client, login):
    payee_id = add_payee(client, login)
    token = login("officer.ben")
    payment_id = client.post("/payments", token, {"payee_id": payee_id, "amount": "10.00"}).json()["id"]
    response = client.post(f"/payments/{payment_id}/approve", token)
    assert response.status == 403
    assert response.json()["error"] == "self_approval"


def test_validation_errors(client, login):
    token = login("clerk.ana")
    assert client.post("/payments", token, {"amount": "1.00"}).status == 400
    assert client.post("/payments", token, {"payee_id": "1", "amount": "1.00"}).status == 400
    bad_json = client.request("POST", "/payments", token)
    assert bad_json.status == 400
    assert client.get("/reports/daily-totals?day=yesterday", token).status == 400


def test_not_found_payment(client, login):
    assert client.get("/payments/99", login("clerk.ana")).status == 404


def test_idle_privileged_session_expires(client, login, clock):
    token = login("treasury.dee")
    clock.advance(minutes=20)
    assert client.get("/payments/1/release", token).status == 405
    assert client.post("/payments/1/release", token).json()["error"] == "session_expired"


def test_activity_keeps_a_session_alive(client, login, clock):
    token = login("clerk.ana")
    for _ in range(3):
        clock.advance(minutes=25)
        assert client.get("/payments", token).status == 200


def test_payee_endpoints(client, login):
    payee_id = add_payee(client, login)
    summary = client.get(f"/payees/{payee_id}", login("clerk.ana")).json()
    assert summary["account_number"] == "****5678"
    listing = client.get("/payees?name=North", login("clerk.ana")).json()
    assert [p["id"] for p in listing] == [payee_id]
    number = client.get(f"/payees/{payee_id}/account-number", login("treasury.dee")).json()
    assert number["account_number"] == "880012345678"
    hold = client.post(f"/payees/{payee_id}/legal-hold", login("admin.gus"), {"hold": True})
    assert hold.json()["legal_hold"] is True
    assert client.post(f"/payees/{payee_id}/legal-hold", login("admin.gus"), {"hold": "yes"}).status == 400
    assert client.post(f"/payees/{payee_id}/close", login("officer.ben")).json()["status"] == "closed"


def test_statement_and_ledger_are_csv(client, login):
    payee_id = add_payee(client, login)
    client.post("/payments", login("clerk.ana"), {"payee_id": payee_id, "amount": "10.00", "memo": "Invoice 7"})
    statement = client.get(f"/payees/{payee_id}/statement?period=2026-09", login("clerk.ana"))
    assert statement.headers["Content-Type"].startswith("text/csv")
    assert "Invoice 7" in statement.text
    delivered = client.post(f"/payees/{payee_id}/statement/deliver", login("clerk.ana"), {"period": "2026-09"})
    assert delivered.status == 202
    ledger = client.get("/ledger/export", login("auditor.fay"))
    assert ledger.text.startswith("payment_id,")


def test_reports_audit_and_admin_routes(client, login):
    add_payee(client, login)
    totals = client.get("/reports/daily-totals?day=2026-09-01", login("auditor.fay"))
    assert totals.status == 200
    events = client.get("/audit/events", login("auditor.fay")).json()
    assert events[0]["action"] == "add_payee"
    assert client.post("/users", login("admin.gus"), {"user_id": "clerk.hal", "role": "clerk"}).status == 201
    assert client.post("/keys/rotate", login("admin.gus")).json() == {"key_version": 2}
    assert client.post("/retention/run", login("admin.gus")).json()["payees_purged"] == []


def test_memo_amendment_route(client, login):
    payee_id = add_payee(client, login)
    token = login("clerk.ana")
    payment_id = client.post("/payments", token, {"payee_id": payee_id, "amount": "10.00"}).json()["id"]
    response = client.put(f"/payments/{payment_id}/memo", token, {"memo": "Invoice 8"})
    assert response.json()["memo"] == "Invoice 8"


def test_unexpected_errors_are_hidden(client, login, service, monkeypatch):
    def broken(actor):
        raise RuntimeError("boom 880012345678")

    monkeypatch.setattr(service, "list_payments", broken)
    response = client.get("/payments", login("clerk.ana"))
    assert response.status == 500
    assert response.json() == {"error": "internal_error"}
