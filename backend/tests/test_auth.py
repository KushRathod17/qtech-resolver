"""Auth, roles, and the privilege-escalation hole closed in Slice 0."""
from tests.conftest import auth, _register, TEST_ORG_NAME, TEST_ORG_JOIN_CODE, TEST_INVITE_CODE


def _join_payload(client, **overrides):
    orgs = client.get("/organizations/search", params={"name": TEST_ORG_NAME}).json()
    payload = {
        "email": "someone@qtechtest.io",
        "full_name": "Someone",
        "password": "password123",
        "organization_id": orgs[0]["id"],
        "join_code": TEST_ORG_JOIN_CODE,
        "invite_code": TEST_INVITE_CODE,
    }
    payload.update(overrides)
    return payload


def test_first_account_becomes_admin(client):
    """The first person to join a freshly created organization becomes its
    admin -- there's nobody else yet to have granted them the role."""
    user = _register(client, "first@qtechtest.io", "First")
    assert user["role"] == "admin"


def test_second_account_is_a_developer(client, admin):
    user = _register(client, "second@qtechtest.io", "Second")
    assert user["role"] == "developer"


def test_registration_cannot_grant_a_role(client, admin):
    """The hole: anyone could once register themselves as an admin."""
    r = client.post(
        "/auth/signup/join",
        json=_join_payload(client, email="sneaky@qtechtest.io", full_name="Sneaky", role="admin"),
    )
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers=auth(token))
    assert me.json()["role"] == "developer"


def test_profile_edit_cannot_grant_a_role(client, dev):
    """And the same hole from the other direction."""
    client.patch("/users/me", json={"full_name": "Dev", "role": "admin"}, headers=auth(dev["token"]))
    me = client.get("/auth/me", headers=auth(dev["token"])).json()
    assert me["role"] == "developer"


def test_duplicate_email_is_rejected(client, admin):
    r = client.post(
        "/auth/signup/join",
        json=_join_payload(client, email="admin@qtechtest.io", full_name="Clone"),
    )
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()


def test_login_and_me(client, admin):
    me = client.get("/auth/me", headers=auth(admin["token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "admin@qtechtest.io"


def test_bad_password_is_401(client, admin):
    r = client.post(
        "/auth/login",
        data={"username": "admin@qtechtest.io", "password": "wrong"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 401


def test_unauthenticated_requests_are_401(client):
    assert client.get("/tickets/").status_code == 401


def test_only_admins_change_roles(client, manager, dev):
    r = client.patch(
        f"/users/{dev['id']}/role", json={"role": "admin"}, headers=auth(manager["token"])
    )
    assert r.status_code == 403


def test_the_last_admin_cannot_demote_themselves(client, admin):
    """Otherwise you lock everyone out of the workspace with one dropdown."""
    r = client.patch(
        f"/users/{admin['id']}/role", json={"role": "developer"}, headers=auth(admin["token"])
    )
    assert r.status_code == 400
    assert "only remaining admin" in r.json()["detail"]


# ---------------------------------------------------------------- passwords

def test_password_change_requires_the_current_one(client, dev):
    r = client.post(
        "/users/me/password",
        json={"current_password": "wrong", "new_password": "brandnew123"},
        headers=auth(dev["token"]),
    )
    assert r.status_code == 400


def test_password_change_then_login(client, dev):
    r = client.post(
        "/users/me/password",
        json={"current_password": "password123", "new_password": "brandnew123"},
        headers=auth(dev["token"]),
    )
    assert r.status_code == 204

    old = client.post(
        "/auth/login",
        data={"username": "dev@qtechtest.io", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert old.status_code == 401

    new = client.post(
        "/auth/login",
        data={"username": "dev@qtechtest.io", "password": "brandnew123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert new.status_code == 200


def test_password_must_be_at_least_8_chars(client, admin):
    r = client.post(
        "/auth/signup/join",
        json=_join_payload(client, email="short@qtechtest.io", full_name="Short", password="abc"),
    )
    assert r.status_code == 422


def test_password_over_72_bytes_is_rejected(client, admin):
    """bcrypt silently truncates past 72 bytes — refuse rather than truncate."""
    r = client.post(
        "/auth/signup/join",
        json=_join_payload(client, email="long@qtechtest.io", full_name="Long", password="a" * 100),
    )
    assert r.status_code == 422
