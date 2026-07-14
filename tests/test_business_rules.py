import pytest


def test_cannot_rent_broken_hardware(client, member_headers):
    response = client.post("/api/hardware/5/rent", headers=member_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Damaged hardware cannot be rented"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/users", {"name": "Mallory", "email": "m@booksy.com", "password": "Password1!", "role": "admin"}),
        ("post", "/api/hardware", {"name": "Rogue laptop", "brand": "Acme", "status": "Available"}),
        ("delete", "/api/hardware/1", None),
        ("patch", "/api/hardware/1/repair", {}),
        ("get", "/api/users", None),
    ],
)
def test_members_are_refused_every_admin_route(client, member_headers, method, path, body):
    call = getattr(client, method)
    response = call(path, headers=member_headers, **({"json": body} if body is not None else {}))

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_routes_reject_anonymous_callers(client):
    assert client.get("/api/users").status_code == 401
    assert client.post("/api/hardware/1/rent").status_code == 401


def test_serial_number_and_category_round_trip_and_serials_stay_unique(client, admin_headers):
    device = {
        "name": "MacBook Pro 16",
        "brand": "Apple",
        "serial_number": "MBP-2024-001",
        "category": "Laptop",
        "status": "Available",
    }
    created = client.post("/api/hardware", headers=admin_headers, json=device)
    duplicate = client.post("/api/hardware", headers=admin_headers, json={**device, "name": "Another MacBook"})
    bad_category = client.post(
        "/api/hardware", headers=admin_headers,
        json={**device, "serial_number": "MBP-2024-002", "category": "Spaceship"},
    )

    assert created.status_code == 201
    assert created.json()["serial_number"] == "MBP-2024-001"
    assert created.json()["category"] == "Laptop"
    assert duplicate.status_code == 409
    assert "serial number" in duplicate.json()["detail"]
    assert bad_category.status_code == 422


def test_cannot_rent_hardware_already_in_use(client, member_headers):
    response = client.post("/api/hardware/2/rent", headers=member_headers)

    assert response.status_code == 409
    assert "In Use" in response.json()["detail"]


def test_rent_then_return_tracks_owner_and_state(client, member_headers):
    rented = client.post("/api/hardware/1/rent", headers=member_headers)
    returned = client.post("/api/hardware/1/return", headers=member_headers)

    assert rented.status_code == 200
    assert rented.json()["status"] == "In Use"
    assert rented.json()["assigned_to"] == "member@booksy.com"
    assert returned.status_code == 200
    assert returned.json()["status"] == "Available"
    assert returned.json()["assigned_to"] is None


def test_damage_hold_requires_explicit_repair_resolution(client, admin_headers):
    sent_to_repair = client.patch("/api/hardware/5/repair", headers=admin_headers)
    unsafe_completion = client.patch("/api/hardware/5/repair", headers=admin_headers)
    resolved = client.patch(
        "/api/hardware/5/repair",
        headers=admin_headers,
        json={"resolve_damage": True, "resolution_note": "Battery replaced and hardware safety-tested."},
    )

    assert sent_to_repair.status_code == 200
    assert sent_to_repair.json()["status"] == "Repair"
    assert sent_to_repair.json()["is_damaged"] is True
    assert unsafe_completion.status_code == 409
    assert "explicit repair resolution" in unsafe_completion.json()["detail"]
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "Available"
    assert resolved.json()["is_damaged"] is False
    assert "Battery replaced" in resolved.json()["history"]


def test_sqlite_allocates_new_hardware_ids(client, admin_headers):
    base = {"brand": "Framework", "purchase_date": "2026-01-10", "status": "Available"}
    first = client.post("/api/hardware", headers=admin_headers, json={**base, "name": "Laptop A"})
    second = client.post("/api/hardware", headers=admin_headers, json={**base, "name": "Laptop B"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
