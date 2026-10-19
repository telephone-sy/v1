from io import BytesIO

from PIL import Image

from conftest import create_listing, login, make_admin, register


def test_register_login_and_reject_wrong_password(client):
    user = register(client)
    assert "password_hash" not in user
    client.post("/api/auth/logout")
    assert login(client).status_code == 200
    client.post("/api/auth/logout")
    bad = client.post("/api/auth/login", json={"phone": "0912345678", "password": "wrong"})
    assert bad.status_code == 401
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/auth/me").json() is None


def test_registration_rejects_invalid_phone_and_short_password(client):
    invalid_phone = client.post("/api/auth/register", json={"name":"مستخدم", "phone":"123", "password":"LongPass1234"})
    short_password = client.post("/api/auth/register", json={"name":"مستخدم", "phone":"0911111111", "password":"short"})
    assert invalid_phone.status_code == 422
    assert short_password.status_code == 422


def test_listing_create_validation_currency_and_filter(client):
    register(client)
    assert create_listing(client).status_code == 201
    assert create_listing(client, price="12000000", currency="SYP", model="iPhone 14").status_code == 201
    invalid = create_listing(client, price="0")
    assert invalid.status_code == 422
    assert client.get("/api/listings", params={"min_price": 500}).status_code == 422
    assert client.get("/api/listings", params={"sort": "price_asc"}).status_code == 422
    assert "/api/listings/{listing_id}" in client.get("/openapi.json").json()["paths"]
    usd = client.get("/api/listings", params={"currency": "USD", "min_price": 500}).json()
    assert len(usd) == 1
    assert usd[0]["price"] == "750.00"
    assert usd[0]["currency"] == "USD"
    syp = client.get("/api/listings", params={"currency": "SYP", "min_price": 500}).json()
    assert len(syp) == 1
    assert syp[0]["price"] == "12000000.00"
    results = client.get("/api/listings", params={"q": "iPhone 14", "city": "دمشق", "condition": "used"}).json()
    assert len(results) == 1 and results[0]["model"] == "iPhone 14"


def test_owner_can_edit_delete_but_other_user_cannot(client):
    register(client)
    listing = create_listing(client).json()
    client.post("/api/auth/logout")
    register(client, "0987654321", "مستخدم ثان")
    assert client.patch(f"/api/listings/{listing['id']}", json={"model": "معدل"}).status_code == 403
    assert client.delete(f"/api/listings/{listing['id']}").status_code == 403
    client.post("/api/auth/logout")
    login(client)
    assert client.patch(f"/api/listings/{listing['id']}", json={"model": "iPhone 16"}).json()["title"] == "Apple iPhone 16"
    assert client.delete(f"/api/listings/{listing['id']}").status_code == 204
    assert client.get(f"/api/listings/{listing['id']}").status_code == 404


def test_sold_favorites_and_reports(client):
    register(client)
    listing = create_listing(client).json()
    item_id = listing["id"]
    assert client.patch(f"/api/listings/{item_id}/sold").json()["is_sold"] is True
    assert client.post(f"/api/favorites/{item_id}").status_code == 201
    assert len(client.get("/api/favorites").json()) == 1
    assert client.delete(f"/api/favorites/{item_id}").status_code == 204
    assert client.get("/api/favorites").json() == []
    report = client.post("/api/reports", json={"listing_id": item_id, "reason": "سعر مخالف"})
    assert report.status_code == 201


def test_region_filter_is_saved_and_returned(client):
    register(client)
    created = create_listing(client, city="الحسكة", region="قامشلو")
    assert created.status_code == 201, created.text
    assert created.json()["region"] == "قامشلو"
    filtered = client.get("/api/listings", params={"city":"الحسكة", "region":"قامشلو"}).json()
    assert len(filtered) == 1 and filtered[0]["region"] == "قامشلو"


def test_admin_routes_are_server_authorized_and_redact_hashes(client):
    register(client)
    assert client.get("/api/admin/stats").status_code == 403
    client.post("/api/auth/logout")
    make_admin(client)
    users = client.get("/api/admin/users")
    assert users.status_code == 200
    assert all("password_hash" not in user for user in users.json())
    assert client.get("/api/admin/actions").status_code == 200


def test_disabling_user_revokes_old_sessions_even_after_reactivation(client):
    target = register(client)
    old_token = client.cookies.get("telephone_sy_session")
    client.post("/api/auth/logout")
    make_admin(client)
    admin_token = client.cookies.get("telephone_sy_session")

    disabled = client.patch(f"/api/admin/users/{target['id']}/active?active=false")
    assert disabled.status_code == 200
    client.cookies.set("telephone_sy_session", old_token)
    assert client.get("/api/auth/me").json() is None

    client.cookies.set("telephone_sy_session", admin_token)
    assert client.patch(f"/api/admin/users/{target['id']}/active?active=true").status_code == 200
    client.cookies.set("telephone_sy_session", old_token)
    assert client.get("/api/auth/me").json() is None


def test_mutation_rejects_cross_origin_requests(client):
    response = client.post("/api/auth/logout", headers={"Origin":"https://attacker.example"})
    assert response.status_code == 403


def test_images_are_validated_reencoded_and_rejected_when_mime_wrong(client):
    register(client)
    listing = create_listing(client).json()
    image_bytes = BytesIO()
    Image.new("RGB", (12, 12), color="red").save(image_bytes, format="PNG")
    accepted = client.post(
        f"/api/listings/{listing['id']}/images",
        files=[("files", ("phone.png", image_bytes.getvalue(), "image/png"))],
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["images"][0].endswith(".jpg")
    denied = client.post(
        f"/api/listings/{listing['id']}/images",
        files=[("files", ("phone.png", b"not an image", "image/png"))],
    )
    assert denied.status_code == 415
    too_many = client.post(
        f"/api/listings/{listing['id']}/images",
        files=[("files", (f"{index}.png", b"", "image/png")) for index in range(6)],
    )
    assert too_many.status_code == 413
    assert client.get(f"/api/listings/{listing['id']}").json()["images"] == accepted.json()["images"]