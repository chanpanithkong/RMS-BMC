from sqlalchemy import text

from tests.conftest import PASSWORD


def test_health_reaches_database(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "ok"}


def test_login_me_and_refresh_rotation(client):
    r = client.post("/api/v1/auth/login", json={"username": "cashier", "password": PASSWORD})
    assert r.status_code == 200
    assert "refresh_token" not in r.json()  # refresh token only travels in the HttpOnly cookie
    assert "httponly" in r.headers["set-cookie"].lower()
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["username"] == "cashier" and "payments.create" in me["permissions"] and me["limits"]["discount_pct"] == "10.0000"
    old_cookie = client.cookies.get("rms_refresh")
    r2 = client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200 and client.cookies.get("rms_refresh") != old_cookie
    # Reusing the rotated token revokes every session (theft response).
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_cookie})
    assert r3.status_code == 401 and r3.json()["error"]["code"] == "REFRESH_REUSED"


def test_wrong_password_is_generic_and_locks_after_five(client):
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"username": "waiter", "password": "nope-nope-nope"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = client.post("/api/v1/auth/login", json={"username": "waiter", "password": PASSWORD})
    assert r.status_code == 423 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_unknown_user_gets_same_error(client):
    r = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "whatever-123"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_unauthenticated_and_logout(client, api):
    assert client.get("/api/v1/auth/me").status_code == 401
    cashier = api("cashier")
    assert cashier.post("/auth/logout").status_code == 200
    r = cashier.get("/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_REVOKED"


def test_change_password_policy(api):
    u = api("cashier")
    r = u.post("/auth/password/change", json={"current_password": PASSWORD, "new_password": "cashier"})
    assert r.status_code == 422
    r = u.post("/auth/password/change", json={"current_password": PASSWORD, "new_password": "a-much-longer-one-1"})
    assert r.status_code == 200


def test_forgot_password_does_not_reveal_accounts(client, engine):
    a = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "cashier"}).json()
    b = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "nobody"}).json()
    assert a == b
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from outbox_events where event_type='email.password_reset'")).scalar() == 1


def test_unknown_fields_are_rejected(client):
    r = client.post("/api/v1/auth/login", json={"username": "x", "password": "y", "admin": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_permissions_enforced_by_backend(api):
    waiter = api("waiter")
    r = waiter.get("/users")
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_admin_creates_user_but_cannot_self_grant(api, seeded):
    admin = api("admin")
    body = {"username": "newcashier", "full_name": "New Cashier", "role_codes": ["CASHIER"], "branch_ids": [str(seeded["branch_id"])], "temporary_password": "Temporary-pass-1"}
    r = admin.post("/users", json=body)
    assert r.status_code == 201 and r.json()["must_change_password"] is True
    assert admin.post("/users", json=body).status_code == 409
    me_id = str(seeded["users"]["admin"])
    r = admin.patch(f"/users/{me_id}", json={"role_codes": ["OWNER"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_GRANT"


def test_deactivation_revokes_sessions(api, seeded):
    cashier = api("cashier")
    admin = api("admin")
    r = admin.post(f"/users/{seeded['users']['cashier']}/deactivate", json={"reason": "Left the company"})
    assert r.status_code == 200
    assert cashier.get("/auth/me").status_code == 401


def test_approval_rules(api, seeded):
    cashier = api("cashier")
    # approver must differ from requester
    r = cashier.post("/approvals", json={"action": "discount", "approver_username": "cashier", "approver_secret": "2468", "amount": "20"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_APPROVAL"
    # supervisor limit is 20%
    assert cashier.post("/approvals", json={"action": "discount", "approver_username": "supv", "approver_secret": "7314", "amount": "25"}).json()["error"]["code"] == "APPROVER_LIMIT_EXCEEDED"
    r = cashier.post("/approvals", json={"action": "discount", "approver_username": "supv", "approver_secret": "7314", "amount": "20"})
    assert r.status_code == 201
    # wrong PIN
    assert cashier.post("/approvals", json={"action": "discount", "approver_username": "supv", "approver_secret": "0000", "amount": "5"}).status_code == 403
