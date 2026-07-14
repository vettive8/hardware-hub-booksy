import json

from backend.app.database import connect
from backend.app.seed import load_seed


def test_duplicate_id_is_rejected_without_overwriting_first_record(tmp_path):
    seed = [
        {"id": 4, "name": "Original phone", "brand": "Samsung", "purchaseDate": "2023-01-01", "status": "Available"},
        {"id": 4, "name": "Duplicate laptop", "brand": "Lenovo", "purchaseDate": "2023-02-01", "status": "Repair"},
    ]
    seed_path = tmp_path / "seed.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")
    db_path = tmp_path / "seed.db"

    report = load_seed(seed_path, db_path)
    with connect(db_path) as db:
        stored = db.execute("SELECT name FROM hardware WHERE id = 4").fetchone()
        count = db.execute("SELECT COUNT(*) AS count FROM hardware").fetchone()["count"]

    assert report.inserted == 1
    assert report.rejected == 1
    assert any(issue.code == "duplicate_id" for issue in report.issues)
    assert count == 1
    assert stored["name"] == "Original phone"

