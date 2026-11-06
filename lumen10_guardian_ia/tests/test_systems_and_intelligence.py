from datetime import datetime, timezone

from guardian.db import now, uid
from guardian.monitor import Monitor
from guardian.threat_intelligence import KEV_URL, PHP_URL, ThreatIntelligence, ThreatScheduler, latest_slot
from guardian.workflow import record_event


def test_multiple_systems_group_sources_and_reject_cross_tenant_links(system):
    app, client, tenant, _ = system
    first = client.post("/api/v1/systems", json={"name": "Moodle"}).json()["id"]
    second = client.post("/api/v1/systems", json={"name": "Store"}).json()["id"]
    one = client.post(
        "/api/v1/environments",
        json={"name": "Moodle HTTP", "kind": "http", "target": "https://example.invalid/health", "system_id": first},
    ).json()["id"]
    two = client.post(
        "/api/v1/environments",
        json={"name": "Store HTTP", "kind": "http", "target": "https://example.invalid/status", "system_id": second},
    ).json()["id"]
    assert app.state.store.environment(tenant, one)["system_id"] == first
    assert app.state.store.environment(tenant, two)["system_id"] == second
    other = uid()
    app.state.store.execute("INSERT INTO tenants VALUES(?,?,?)", (other, "Other", now()))
    foreign = uid()
    app.state.store.execute("INSERT INTO systems VALUES(?,?,?,?)", (foreign, other, "Private", now()))
    assert client.put(f"/api/v1/environments/{one}/system/{foreign}").status_code == 404
    assert len(client.get("/api/v1/overview").json()["systems"]) == 2


def test_healthy_monitor_does_not_spend_ai(system):
    app, client, tenant, _ = system
    client.post("/api/v1/system/monitor", json={"active": True})
    Monitor(app.state.store).tick()
    assert not app.state.store.rows("SELECT * FROM jobs")
    assert not app.state.store.rows("SELECT * FROM audit WHERE action='ai.started'")


def test_security_scheduler_two_windows_and_restart_idempotency(system):
    app, client, tenant, _ = system
    client.post("/api/v1/system/monitor", json={"active": True})
    scheduler = ThreatScheduler(app.state.store)
    morning = datetime(2026, 11, 6, 11, 0, tzinfo=timezone.utc)
    scheduler.tick(morning)
    assert not app.state.store.rows("SELECT * FROM jobs WHERE kind='threat_review'")
    evening = datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc)
    scheduler.tick(evening)
    ThreatScheduler(app.state.store).tick(evening)
    assert len(app.state.store.rows("SELECT * FROM jobs WHERE kind='threat_review'")) == 1
    app.state.store.execute("UPDATE jobs SET state='done'")
    scheduler.tick(datetime(2026, 11, 7, 11, 0, tzinfo=timezone.utc))
    assert len(app.state.store.rows("SELECT * FROM jobs WHERE kind='threat_review'")) == 2
    assert latest_slot(datetime(2026, 11, 6, 4, 0, tzinfo=timezone.utc)) == "2026-11-05:20"


def test_advisory_feed_matching_dedup_and_truthful_partial_coverage(system):
    app, _, tenant, env = system

    def fetch(url):
        if url == KEV_URL:
            return {
                "dateReleased": "2026-11-06",
                "vulnerabilities": [
                    {
                        "cveID": "CVE-2026-12345",
                        "vendorProject": "PHP",
                        "product": "PHP runtime",
                        "vulnerabilityName": "Synthetic PHP advisory",
                        "dateAdded": "2026-11-06",
                    }
                ],
            }
        if url == PHP_URL:
            return {"8": {"supported_versions": ["8.3"]}}
        return {"version": "8.3.99", "tags": ["security"], "date": "06 Nov 2026"}

    intel = ThreatIntelligence(app.state.store, fetch)
    collection = intel.collect(tenant)
    assert len(collection["findings"]) == 2 and all(f["new"] for f in collection["findings"])
    diagnosis = {"summary": "Synthetic contract test, not real threat validation", "cause": "Test", "risk": "high"}
    intel.complete(tenant, env, collection, diagnosis)
    assert all(not f["new"] for f in intel.collect(tenant)["findings"])
    outbox = app.state.store.rows("SELECT * FROM notification_outbox WHERE action='security.advisory'")
    assert len(outbox) == 1

    def fail(url):
        raise OSError("offline")

    failed = ThreatIntelligence(app.state.store, fail).collect(tenant)
    assert all(s["status"] == "unavailable" for s in failed["sources"])
    assert failed["findings"] == []


def test_light_errors_trigger_incident_without_one_email_per_timestamp(system):
    app, _, tenant, env = system
    first = record_event(app.state.store, tenant, env, "php_warning", "[06-Nov-2026 11:10:10] Warning: example", "P3")
    second = record_event(app.state.store, tenant, env, "php_warning", "[06-Nov-2026 11:10:11] Warning: example", "P3")
    assert first == second
    assert app.state.store.one("SELECT severity FROM incidents WHERE id=?", (first,))["severity"] == "P3"
    assert len(app.state.store.rows("SELECT * FROM notification_outbox WHERE action='incident.detected'")) == 1
