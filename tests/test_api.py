import pytest
from fastapi.testclient import TestClient

from app.main import app, detector

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    detector.reset()
    yield
    detector.reset()


def feed_baseline(service="checkout-api", metric="latency_ms", n=12):
    for i in range(n):
        client.post("/ingest", json={"service": service, "metric": metric, "value": 100 + (i % 3)})


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_normal_samples_do_not_trigger_incidents():
    feed_baseline()
    r = client.post("/ingest", json={"service": "checkout-api", "metric": "latency_ms", "value": 101})
    assert r.json()["anomaly"] is False
    assert client.get("/incidents").json()["count"] == 0


def test_spike_creates_critical_incident_with_runbook():
    feed_baseline()
    r = client.post("/ingest", json={"service": "checkout-api", "metric": "latency_ms", "value": 900})
    body = r.json()
    assert body["anomaly"] is True
    assert body["incident"]["severity"] == "critical"
    assert "downstream" in body["incident"]["suggestion"].lower()


def test_no_alert_before_enough_history():
    r = client.post("/ingest", json={"service": "new-svc", "metric": "cpu_percent", "value": 99})
    assert r.json()["anomaly"] is False


def test_services_are_tracked_independently():
    feed_baseline(service="svc-a")
    r = client.post("/ingest", json={"service": "svc-b", "metric": "latency_ms", "value": 900})
    assert r.json()["anomaly"] is False


def test_incident_filter_by_severity():
    feed_baseline()
    client.post("/ingest", json={"service": "checkout-api", "metric": "latency_ms", "value": 900})
    assert client.get("/incidents?severity=critical").json()["count"] == 1
    assert client.get("/incidents?severity=warning").json()["count"] == 0


def test_validation_rejects_bad_payload():
    r = client.post("/ingest", json={"service": "", "metric": "x", "value": "abc"})
    assert r.status_code == 422


def test_metrics_endpoint_exposes_counters():
    feed_baseline(n=9)
    client.post("/ingest", json={"service": "checkout-api", "metric": "latency_ms", "value": 900})
    text = client.get("/metrics").text
    assert "aiops_samples_total" in text
    assert "aiops_incidents_total" in text
