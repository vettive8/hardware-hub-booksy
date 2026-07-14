from backend.app import auditor


def test_audit_without_api_key_keeps_every_rule_finding(client, member_headers, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    response = client.post("/api/audit", headers=member_headers)
    body = response.json()

    assert response.status_code == 200
    assert body["mode"] == "rules"
    assert body["summary"]["total"] == 9
    assert body["summary"]["rule_findings"] == 9
    assert {finding["source"] for finding in body["findings"]} == {"rules"}
    assert body["llm_status"]["state"] == "not_configured"


def test_unknown_llm_ids_are_dropped_and_rule_duplicates_win(client, member_headers, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        auditor,
        "request_llm_audit",
        lambda _evidence: {
            "findings": [
                {
                    "code": "invented_device_issue",
                    "severity": "high",
                    "hardware_id": 999,
                    "title": "Invented device",
                    "explanation": "This identifier was not supplied.",
                    "evidence": {"id": 999},
                },
                {
                    "code": "duplicate_id",
                    "severity": "low",
                    "hardware_id": 4,
                    "title": "Duplicate restatement",
                    "explanation": "The rule engine already proved this.",
                    "evidence": {"id": 4},
                },
                {
                    "code": "warranty_gap",
                    "severity": "low",
                    "hardware_id": 1,
                    "title": "Warranty information absent",
                    "explanation": "No warranty metadata is present for this accepted item.",
                    "evidence": {"name": "Apple iPhone 13 Pro Max"},
                },
            ]
        },
    )

    body = client.post("/api/audit", headers=member_headers).json()

    assert body["mode"] == "rules+llm"
    assert body["summary"]["rule_findings"] == 9
    assert body["summary"]["total"] == 10
    assert body["hallucination_guard"] == {"dropped_unknown_ids": 1, "dropped_rule_duplicates": 1}
    assert body["llm_status"]["accepted_findings"] == 1
    duplicate = [finding for finding in body["findings"] if finding["code"] == "duplicate_id"]
    assert len(duplicate) == 1
    assert duplicate[0]["source"] == "rules"
    assert all(finding["hardware_id"] != 999 for finding in body["findings"])


def test_invalid_llm_schema_fails_back_to_rules(client, member_headers, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        auditor,
        "request_llm_audit",
        lambda _evidence: {
            "findings": [
                {
                    "code": "bad_severity",
                    "severity": "catastrophic",
                    "hardware_id": 1,
                    "title": "Invalid severity",
                    "explanation": "This must fail the allowed severity enum.",
                    "evidence": {},
                }
            ]
        },
    )

    body = client.post("/api/audit", headers=member_headers).json()

    assert body["mode"] == "rules-fallback"
    assert body["summary"]["total"] == 9
    assert body["llm_status"]["state"] == "invalid_response"

