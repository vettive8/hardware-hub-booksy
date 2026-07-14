import json
import os

import pytest

from backend.app import auditor


def provider(*findings):
    """Stand in for a provider response without spending anything."""
    return lambda _evidence: auditor.ProviderAuditResult(
        model="anthropic/claude-haiku-4.5",
        payload={"findings": list(findings)},
    )


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


def test_audit_can_force_rules_only_with_a_local_key_present(client, member_headers, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "local-key-that-must-not-be-used")
    monkeypatch.setenv("OPENROUTER_DISABLED", "1")
    monkeypatch.setattr(
        auditor,
        "request_llm_audit",
        lambda _evidence: (_ for _ in ()).throw(AssertionError("provider must remain disabled")),
    )

    body = client.post("/api/audit", headers=member_headers).json()

    assert body["mode"] == "rules"
    assert body["summary"]["total"] == 9
    assert body["llm_status"]["state"] == "disabled"


def test_model_never_sees_the_rule_engines_conclusions(client, member_headers, monkeypatch):
    """The model must audit independently. Handing it the loader's codes and messages
    is what made it restate them and contribute nothing."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_DISABLED", raising=False)
    captured = {}

    def capture(evidence):
        captured["payload"] = auditor.model_evidence(evidence)
        return auditor.ProviderAuditResult(model="test", payload={"findings": []})

    monkeypatch.setattr(auditor, "request_llm_audit", capture)
    client.post("/api/audit", headers=member_headers)

    payload = captured["payload"]
    serialized = json.dumps(payload)
    assert set(payload) == {"accepted_inventory", "raw_source_rows"}
    # The rejected records must still reach the model, or it is blind to the real traps.
    assert "Appel" in serialized and "Unknown" in serialized and "22-05-2023" in serialized
    # ...but never the loader's own answers.
    assert "duplicate_id" not in serialized
    assert "Duplicate hardware id" not in serialized


def test_agreement_is_corroboration_and_new_findings_are_kept(client, member_headers, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_DISABLED", raising=False)
    monkeypatch.setattr(
        auditor,
        "request_llm_audit",
        provider(
            {
                "code": "duplicate_id",
                "severity": "high",
                "hardware_id": 4,
                "title": "Two records share id 4",
                "explanation": "The model independently reached the same conclusion as the rule engine.",
                "evidence": "id 4 appears twice in the source file",
            },
            {
                "code": "other",
                "severity": "low",
                "hardware_id": 3,
                "title": "Stalled in repair since 2021",
                "explanation": "A finding no schema rule can express.",
                "evidence": "Razer Basilisk V2 · status Repair · purchased 2021-06-05",
            },
        ),
    )

    body = client.post("/api/audit", headers=member_headers).json()
    guard = body["hallucination_guard"]

    assert body["mode"] == "rules+llm"
    assert guard["corroborated"] == 1
    assert guard["model_only"] == 1
    assert guard["rules_only"] == 8
    assert body["summary"]["total"] == 10

    duplicate = next(f for f in body["findings"] if f["code"] == "duplicate_id")
    assert duplicate["source"] == "rules", "rules stay authoritative"
    assert duplicate["confidence"] == "corroborated"

    novel = next(f for f in body["findings"] if f["code"] == "other")
    assert novel["source"] == "llm"
    assert novel["confidence"] == "model_only"


def test_one_malformed_finding_is_quarantined_not_the_whole_batch(client, member_headers, monkeypatch):
    """Same policy the seed loader applies to a bad record: drop the row, keep the batch."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_DISABLED", raising=False)
    monkeypatch.setattr(
        auditor,
        "request_llm_audit",
        provider(
            {
                "code": "BAD-CODE",  # outside the shared taxonomy
                "severity": "high",
                "hardware_id": 1,
                "title": "Malformed finding",
                "explanation": "This one must be quarantined on its own.",
                "evidence": "malformed fixture",
            },
            {
                "code": "other",
                "severity": "high",
                "hardware_id": 999,  # never existed
                "title": "Hallucinated device",
                "explanation": "This identifier was never supplied.",
                "evidence": "invented identifier 999",
            },
            {
                "code": "other",
                "severity": "low",
                "hardware_id": 1,
                "title": "No warranty metadata",
                "explanation": "A valid finding that must survive its malformed siblings.",
                "evidence": "Apple iPhone 13 Pro Max has no warranty field",
            },
        ),
    )

    body = client.post("/api/audit", headers=member_headers).json()
    guard = body["hallucination_guard"]

    assert body["mode"] == "rules+llm"
    assert guard["dropped_invalid_schema"] == 1
    assert guard["dropped_unknown_ids"] == 1
    assert guard["model_only"] == 1
    assert body["summary"]["total"] == 10
    assert all(finding["hardware_id"] != 999 for finding in body["findings"])
    assert any(finding["title"] == "No warranty metadata" for finding in body["findings"])


def test_unusable_envelope_falls_back_to_rules(client, member_headers, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_DISABLED", raising=False)
    monkeypatch.setattr(
        auditor,
        "request_llm_audit",
        lambda _evidence: auditor.ProviderAuditResult(model="test", payload={"nonsense": True}),
    )

    body = client.post("/api/audit", headers=member_headers).json()

    assert body["mode"] == "rules-fallback"
    assert body["summary"]["total"] == 9
    assert body["llm_status"]["state"] == "failed"


def test_findings_expose_one_evidence_type(client, member_headers, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    body = client.post("/api/audit", headers=member_headers).json()

    assert all(isinstance(finding["evidence"], str) for finding in body["findings"])


def test_wire_schema_uses_portable_strict_subset():
    unsupported = {"pattern", "minLength", "maxLength", "minItems", "maxItems", "default"}

    def assert_schema(node):
        if isinstance(node, dict):
            assert unsupported.isdisjoint(node)
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for value in node.values():
                assert_schema(value)
        elif isinstance(node, list):
            for value in node:
                assert_schema(value)

    assert_schema(auditor.WIRE_AUDIT_SCHEMA)


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY is not configured")
def test_live_openrouter_audit_validates_and_uses_source_ids(client, member_headers):
    response = client.post("/api/audit", headers=member_headers)
    body = response.json()
    source_ids = {1, 2, 3, 4, 5, 6, 7, 9, 10, 11}

    assert response.status_code == 200
    assert body["mode"] == "rules+llm", body["llm_status"]
    assert body["llm_status"]["state"] == "succeeded"
    assert all(
        finding["hardware_id"] is None or finding["hardware_id"] in source_ids
        for finding in body["findings"]
    )
    print(
        json.dumps(
            {
                "model": body["model"],
                "llm_status": body["llm_status"],
                "hallucination_guard": body["hallucination_guard"],
                "model_findings": [f for f in body["findings"] if f["source"] == "llm"],
            },
            indent=2,
        )
    )
