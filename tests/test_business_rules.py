def test_cannot_rent_broken_hardware(client, member_headers):
    response = client.post("/api/hardware/5/rent", headers=member_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Damaged hardware cannot be rented"


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
