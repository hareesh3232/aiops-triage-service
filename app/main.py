"""AIOps Incident Triage Service: FastAPI app with health checks and Prometheus metrics."""
import logging
import time

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel, Field

from app.detector import Detector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aiops")

app = FastAPI(title="AIOps Incident Triage Service", version="1.0.0")
detector = Detector()
START_TIME = time.time()

SAMPLES_TOTAL = Counter("aiops_samples_total", "Samples ingested", ["service", "metric"])
INCIDENTS_TOTAL = Counter(
    "aiops_incidents_total", "Incidents detected", ["service", "metric", "severity"]
)
UPTIME = Gauge("aiops_uptime_seconds", "Service uptime in seconds")


class Sample(BaseModel):
    service: str = Field(..., min_length=1, examples=["checkout-api"])
    metric: str = Field(..., min_length=1, examples=["latency_ms"])
    value: float


@app.get("/health")
def health():
    """Liveness/readiness probe used by Docker and load balancers."""
    return {"status": "ok", "uptime_seconds": round(time.time() - START_TIME, 1)}


@app.post("/ingest")
def ingest(sample: Sample):
    """Ingest one metric sample; returns an incident if it is anomalous."""
    SAMPLES_TOTAL.labels(sample.service, sample.metric).inc()
    incident = detector.ingest(sample.service, sample.metric, sample.value)
    if incident:
        INCIDENTS_TOTAL.labels(sample.service, sample.metric, incident.severity).inc()
        log.warning(
            "incident service=%s metric=%s severity=%s z=%s",
            incident.service, incident.metric, incident.severity, incident.z_score,
        )
        return {"anomaly": True, "incident": incident.__dict__}
    return {"anomaly": False}


@app.get("/incidents")
def incidents(severity: str | None = None, limit: int = 50):
    """List recent incidents, optionally filtered by severity."""
    items = detector.incidents
    if severity:
        items = [i for i in items if i.severity == severity]
    return {"count": len(items), "incidents": [i.__dict__ for i in items[-limit:]]}


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    UPTIME.set(time.time() - START_TIME)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
