"""Anomaly detection and incident triage logic (pure Python, no I/O)."""
from __future__ import annotations

import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List

WINDOW_SIZE = 30      # samples kept per (service, metric)
MIN_SAMPLES = 8       # samples needed before anomaly scoring starts
Z_WARNING = 3.0
Z_CRITICAL = 5.0

# Suggested first-response runbook step per metric
RUNBOOK = {
    "cpu_percent": "Check for runaway processes and recent deploys; consider scaling out.",
    "memory_percent": "Look for memory leaks; check container limits and restart policy.",
    "latency_ms": "Check downstream dependencies and database slow queries.",
    "error_rate": "Inspect recent deploys and application logs; consider rollback.",
    "disk_percent": "Clean logs/temp files; check log rotation and volume size.",
}
DEFAULT_RUNBOOK = "Investigate recent changes and review service logs."


@dataclass
class Incident:
    service: str
    metric: str
    value: float
    z_score: float
    severity: str
    suggestion: str


@dataclass
class Detector:
    """Rolling z-score detector, one window per (service, metric)."""

    windows: Dict[tuple, Deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=WINDOW_SIZE))
    )
    incidents: List[Incident] = field(default_factory=list)

    def ingest(self, service: str, metric: str, value: float) -> Incident | None:
        window = self.windows[(service, metric)]
        incident = None

        if len(window) >= MIN_SAMPLES:
            mean = statistics.fmean(window)
            std = statistics.pstdev(window)
            # Avoid divide-by-zero on perfectly flat history
            std = max(std, 1e-6, abs(mean) * 0.01)
            z = (value - mean) / std
            severity = self._severity(abs(z))
            if severity:
                incident = Incident(
                    service=service,
                    metric=metric,
                    value=value,
                    z_score=round(z, 2),
                    severity=severity,
                    suggestion=RUNBOOK.get(metric, DEFAULT_RUNBOOK),
                )
                self.incidents.append(incident)

        # Anomalies are not added to the baseline so they don't skew it
        if incident is None:
            window.append(value)
        return incident

    @staticmethod
    def _severity(abs_z: float) -> str | None:
        if abs_z >= Z_CRITICAL:
            return "critical"
        if abs_z >= Z_WARNING:
            return "warning"
        return None

    def reset(self) -> None:
        self.windows.clear()
        self.incidents.clear()
