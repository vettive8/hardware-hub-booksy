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

