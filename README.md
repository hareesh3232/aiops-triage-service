# AIOps Incident Triage Service

A small service that watches operational metrics (latency, CPU, error rate, etc.), detects anomalies with a rolling z-score, and returns a severity plus a suggested first-response runbook step. It is built the way a production service is operated: containerized, tested, CI-checked, observable, and deployable with Infrastructure as Code.

## Why this project
Maps to the GTS focus areas: AIOps, Automation/DevOps, Cloud Operations and SRE/Observability.

## Features
- `POST /ingest` – send a metric sample; anomalies return an incident (`warning` at |z| >= 3, `critical` at |z| >= 5)
- `GET /incidents` – list incidents, filter with `?severity=critical`
- `GET /health` – liveness probe (used by the Docker HEALTHCHECK and CI smoke test)
- `GET /metrics` – Prometheus metrics (`aiops_samples_total`, `aiops_incidents_total`, `aiops_uptime_seconds`)
- Per-service, per-metric baselines; anomalies are kept out of the baseline so it does not drift
- Runbook suggestion per metric type

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
uvicorn app.main:app --reload
```
Docs at http://localhost:8000/docs

## Try it
```bash
# build a baseline
for i in $(seq 1 12); do
  curl -s -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
    -d '{"service":"checkout-api","metric":"latency_ms","value":100}' > /dev/null
done
# send a spike
curl -s -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
  -d '{"service":"checkout-api","metric":"latency_ms","value":900}'
```

## Docker
```bash
docker build -t aiops-triage .
docker run -p 8000:8000 aiops-triage
```
The image runs as a non-root user and includes a HEALTHCHECK.

## CI (GitHub Actions)
`.github/workflows/ci.yml` runs the tests, builds the Docker image, starts the container and smoke-tests `/health` on every push and pull request.

## Deploy on AWS (Terraform)
`terraform/` creates an EC2 instance (Amazon Linux 2023) with Docker installed and a security group that only allows your IP on ports 22 and 8000.
```bash
cd terraform
terraform init
terraform apply -var 'my_ip_cidr=YOUR.IP.ADDR.ESS/32' -var 'key_name=YOUR_KEY_PAIR'
```
Then copy the app to the instance, build and run the container. Run `terraform destroy` when you are done to avoid charges.

## Design notes
- Detector logic (`app/detector.py`) is pure Python, separate from the API layer, so it is easy to unit test.
- A minimum number of samples is required before alerting, to avoid false alarms on new services.
- Standard deviation is floored so a perfectly flat history cannot cause divide-by-zero or hair-trigger alerts.

## Possible next steps
- Prometheus + Grafana dashboard via docker-compose
- Persist incidents in a database
- LLM-generated incident summaries (with guardrails) on top of the rule-based triage
